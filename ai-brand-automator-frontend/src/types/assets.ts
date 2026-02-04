/**
 * Asset types for the Brand Automator platform
 */

/**
 * Pipeline processing status for brand assets
 */
export type PipelineStatus = 'pending' | 'ingested' | 'curated' | 'indexed' | 'failed';

/**
 * File type category
 */
export type FileType = 'image' | 'video' | 'document' | 'other';

/**
 * Brand asset as returned from the API
 */
export interface BrandAsset {
  id: number;
  tenant: number | null;
  company: number;
  file_name: string;
  file_type: FileType;
  file_size: number;
  gcs_path: string;
  gcs_bucket?: string;
  uploaded_at: string;
  processed: boolean;
  pipeline_status: PipelineStatus;
  pipeline_error: string;
  pipeline_trace_id?: string;
}

/**
 * Paginated response for assets list
 */
export interface AssetsListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: BrandAsset[];
}

/**
 * Upload request payload
 */
export interface AssetUploadRequest {
  file: File;
  file_type: FileType;
}

/**
 * Pipeline status display configuration
 */
export interface PipelineStatusConfig {
  label: string;
  icon: string;
  color: string;
  bgColor: string;
}

/**
 * Get display configuration for a pipeline status
 */
export function getPipelineStatusConfig(status: PipelineStatus): PipelineStatusConfig {
  const configs: Record<PipelineStatus, PipelineStatusConfig> = {
    pending: {
      label: 'Pending',
      icon: '🕐',
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-400/20',
    },
    ingested: {
      label: 'Ingested',
      icon: '📥',
      color: 'text-blue-400',
      bgColor: 'bg-blue-400/20',
    },
    curated: {
      label: 'Curated',
      icon: '✨',
      color: 'text-purple-400',
      bgColor: 'bg-purple-400/20',
    },
    indexed: {
      label: 'Indexed',
      icon: '✅',
      color: 'text-green-400',
      bgColor: 'bg-green-400/20',
    },
    failed: {
      label: 'Failed',
      icon: '❌',
      color: 'text-red-400',
      bgColor: 'bg-red-400/20',
    },
  };

  return configs[status] || configs.pending;
}

/**
 * Get file type icon
 */
export function getFileTypeIcon(fileType: FileType): string {
  const icons: Record<FileType, string> = {
    image: '🖼️',
    video: '🎬',
    document: '📄',
    other: '📁',
  };

  return icons[fileType] || icons.other;
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Determine file type from MIME type
 */
export function getFileTypeFromMime(mimeType: string): FileType {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';
  if (
    mimeType === 'application/pdf' ||
    mimeType.includes('document') ||
    mimeType.includes('text/')
  ) {
    return 'document';
  }
  return 'other';
}
