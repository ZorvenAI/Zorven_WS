'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { getPipelineStatusConfig, PipelineStatus } from '@/types/assets';

const POLLING_INTERVAL = 5000; // Poll every 5 seconds

interface UploadedFile {
  id: string;
  file_name: string;
  file_type: string; // Changed from asset_type to match backend
  file_size: number;
  pipeline_status: PipelineStatus;
}

export function AssetUploadForm() {
  const router = useRouter();
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Function to fetch assets
  const fetchAssets = useCallback(async () => {
    try {
      const response = await apiClient.get('/assets/');
      if (response.ok) {
        const data = await response.json();
        const assets = data.results || [];
        setUploadedFiles(assets);
      }
    } catch (error) {
      console.error('Failed to load files:', error);
    }
  }, []);

  // Check if any files are still processing (not indexed or failed)
  const hasPendingFiles = uploadedFiles.some(
    (f) => f.pipeline_status !== 'indexed' && f.pipeline_status !== 'failed'
  );

  // Load existing uploaded files on mount and set up polling
  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  // Set up polling when there are pending files
  useEffect(() => {
    if (hasPendingFiles) {
      pollingRef.current = setInterval(() => {
        fetchAssets();
      }, POLLING_INTERVAL);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [hasPendingFiles, fetchAssets]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found. Please start from step 1.');
        setUploading(false);
        return;
      }

      // Upload each file
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('file_type', getFileType(file.type));

        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/assets/upload/`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
          },
          body: formData,
        });

        if (response.ok) {
          const data = await response.json();
          setUploadedFiles((prev) => [...prev, data]);
        } else {
          const errorData = await response.json();
          setError(`Failed to upload ${file.name}: ${errorData.message || 'Unknown error'}`);
        }
      }
    } catch (error) {
      console.error('Error uploading files:', error);
      setError('An unexpected error occurred. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const getFileType = (mimeType: string): string => {
    if (mimeType.startsWith('image/')) return 'image';
    if (mimeType === 'application/pdf' || mimeType.includes('document')) return 'document';
    if (mimeType.startsWith('video/')) return 'video';
    return 'other';
  };

  const handleSkip = () => {
    router.push('/onboarding/step-5');
  };

  const handleDelete = async (fileId: string, fileName: string) => {
    if (!confirm(`Are you sure you want to delete "${fileName}"?`)) {
      return;
    }

    setDeletingId(fileId);
    setError('');

    try {
      const response = await apiClient.delete(`/assets/${fileId}/`);
      if (response.ok) {
        setUploadedFiles((prev) => prev.filter((f) => f.id !== fileId));
      } else {
        const errorData = await response.json();
        setError(`Failed to delete ${fileName}: ${errorData.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting file:', error);
      setError(`Failed to delete ${fileName}. Please try again.`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleNext = () => {
    if (uploadedFiles.length === 0) {
      setError('Please upload at least one file or click Skip to continue.');
      return;
    }
    router.push('/onboarding/step-5');
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      <div className="border-2 border-dashed border-white/20 rounded-lg p-8 text-center bg-white/5 hover:bg-white/10 hover:border-brand-electric/50 transition-colors">
        <div className="space-y-4">
          <div className="text-brand-silver/70">
            <svg
              className="mx-auto h-12 w-12 text-brand-electric/60"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <label
              htmlFor="file-upload"
              className="relative cursor-pointer rounded-md font-medium text-brand-electric hover:text-brand-electric/80"
            >
              <span>Upload files</span>
              <input
                id="file-upload"
                name="file-upload"
                type="file"
                className="sr-only"
                multiple
                onChange={handleFileUpload}
                accept="image/*,.pdf,.doc,.docx,video/*,.mp4,.mov"
                disabled={uploading}
              />
            </label>
            <p className="text-sm text-brand-silver/70 mt-1">
              or drag and drop
            </p>
          </div>
          <p className="text-xs text-brand-silver/50">
            PNG, JPG, PDF, MP4 up to 50MB each
          </p>
        </div>
      </div>

      {uploading && (
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
          <p className="mt-2 text-sm text-brand-silver/70">Uploading files...</p>
        </div>
      )}

      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-white">Uploaded Files</h3>
            {hasPendingFiles && (
              <span className="text-xs text-brand-silver/70 animate-pulse">
                🔄 Processing...
              </span>
            )}
          </div>
          <ul className="divide-y divide-white/10 border border-white/10 rounded-lg bg-white/5">
            {uploadedFiles.map((file) => (
              <li key={file.id} className="px-4 py-3 flex items-center justify-between">
                <div className="flex items-center">
                  <span className="text-sm font-medium text-white">
                    {file.file_name}
                  </span>
                  <span className="ml-2 text-xs text-brand-silver/70">
                    ({(file.file_size / 1024).toFixed(1)} KB)
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {(() => {
                    const statusConfig = getPipelineStatusConfig(file.pipeline_status || 'pending');
                    return (
                      <span className={`text-xs px-2 py-1 rounded ${statusConfig.bgColor} ${statusConfig.color}`}>
                        {statusConfig.icon} {statusConfig.label}
                      </span>
                    );
                  })()}
                  <span className="text-xs bg-brand-electric/20 text-brand-electric px-2 py-1 rounded">
                    {file.file_type}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleDelete(file.id, file.file_name)}
                    disabled={deletingId === file.id}
                    className="text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title="Delete file"
                  >
                    {deletingId === file.id ? (
                      <span className="inline-block animate-spin">⏳</span>
                    ) : (
                      <span>🗑️</span>
                    )}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-between pt-6">
        <button
          type="button"
          onClick={() => router.push('/onboarding/step-3')}
          className="btn-secondary"
        >
          Back
        </button>
        <div className="space-x-3">
          <button
            type="button"
            onClick={handleSkip}
            className="btn-secondary"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={handleNext}
            disabled={uploading}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next Step
          </button>
        </div>
      </div>
    </div>
  );
}
