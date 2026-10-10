import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { uploadImageMock, getUploadLimitsMock, listPatientsMock } = vi.hoisted(() => ({
  uploadImageMock: vi.fn(),
  getUploadLimitsMock: vi.fn(),
  listPatientsMock: vi.fn(),
}));
vi.mock("@/api/documents", () => ({ uploadImage: uploadImageMock, getUploadLimits: getUploadLimitsMock }));
vi.mock("@/api/patients", () => ({ listAllPatientIds: listPatientsMock }));

import ImageUploader, { formatFileSize, validateImageFile } from "@/components/documents/ImageUploader";

const png = (name = "report.png", size = 2048) => new File([new Uint8Array(size)], name, { type: "image/png" });

beforeEach(() => {
  uploadImageMock.mockReset();
  getUploadLimitsMock.mockResolvedValue({ max_upload_size_mb: 20 });
  listPatientsMock.mockResolvedValue(["P001", "P002"]);
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("validateImageFile", () => {
  it("accepts jpg, jpeg, png and webp", () => {
    for (const name of ["a.jpg", "a.JPEG", "a.png", "a.webp"]) expect(validateImageFile(new File(["x"], name), 20)).toBeNull();
  });
  it("rejects other types, empty files and oversized files", () => {
    expect(validateImageFile(new File(["x"], "a.gif", { type: "image/gif" }), 20)).toMatch(/Only JPG, PNG, and WEBP/);
    expect(validateImageFile(new File(["x"], "a.pdf", { type: "application/pdf" }), 20)).toMatch(/Only JPG/);
    expect(validateImageFile(new File([], "a.png", { type: "image/png" }), 20)).toMatch(/empty/);
    expect(validateImageFile(png("big.png", 3 * 1024 * 1024), 2)).toMatch(/2MB/);
  });
  it("formats sizes", () => {
    expect(formatFileSize(500)).toBe("500 B");
    expect(formatFileSize(2048)).toBe("2 KB");
    expect(formatFileSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("ImageUploader", () => {
  it("shows a preview with name and size, and lets the user remove it", async () => {
    render(<ImageUploader onUploaded={() => {}} />);
    await userEvent.upload(screen.getByLabelText("Choose an image to upload"), png());
    expect(await screen.findByAltText("Preview of report.png")).toBeInTheDocument();
    expect(screen.getByText("report.png")).toBeInTheDocument();
    expect(screen.getByText("2 KB")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(screen.queryByAltText("Preview of report.png")).not.toBeInTheDocument();
  });

  it("rejects an unsupported file with a message and does not select it", async () => {
    render(<ImageUploader onUploaded={() => {}} />);
    await userEvent.upload(screen.getByLabelText("Choose an image to upload"), new File(["x"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Only JPG, PNG, and WEBP/);
    expect(screen.queryByAltText(/Preview of/)).not.toBeInTheDocument();
  });

  it("uploads the file with the chosen patient and reports the result", async () => {
    uploadImageMock.mockResolvedValue({ document_id: "doc-1", file_name: "report.png", status: "VALIDATING", message: "ok", patient_id: null, duplicate: false });
    const onUploaded = vi.fn();
    render(<ImageUploader onUploaded={onUploaded} />);
    await userEvent.upload(screen.getByLabelText("Choose an image to upload"), png());
    await waitFor(() => expect(screen.getByRole("option", { name: "P002" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText(/Patient \(optional\)/), "P002");
    await userEvent.click(screen.getByRole("button", { name: /upload and read text/i }));

    await waitFor(() => expect(onUploaded).toHaveBeenCalled());
    expect(uploadImageMock).toHaveBeenCalledWith(expect.any(File), "P002", expect.any(Function));
    expect(onUploaded.mock.calls[0][0].document_id).toBe("doc-1");
  });

  it("shows the server's error and keeps the selection so the user can retry", async () => {
    const { ApiError } = await import("@/api/client");
    uploadImageMock.mockRejectedValue(new ApiError(422, "'report.png' is not a readable image."));
    render(<ImageUploader onUploaded={() => {}} />);
    await userEvent.upload(screen.getByLabelText("Choose an image to upload"), png());
    await userEvent.click(screen.getByRole("button", { name: /upload and read text/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not a readable image");
    expect(screen.getByText("report.png")).toBeInTheDocument();
  });

  it("disables upload until an image is chosen", () => {
    render(<ImageUploader onUploaded={() => {}} />);
    expect(screen.getByRole("button", { name: /upload and read text/i })).toBeDisabled();
  });
});
