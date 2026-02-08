/**
 * Error thrown when a duplicate file is detected (409 Conflict).
 * Contains the existing asset info so the UI can prompt for replacement.
 *
 * Defined in a shared module to avoid circular imports between
 * api.ts and useAssets.ts.
 */
export class DuplicateFileError extends Error {
  existingAsset: {
    id: number;
    file_name: string;
    file_size: number;
    uploaded_at: string;
    pipeline_status: string;
  };

  constructor(
    message: string,
    existingAsset: DuplicateFileError['existingAsset']
  ) {
    super(message);
    this.name = 'DuplicateFileError';
    this.existingAsset = existingAsset;
  }
}
