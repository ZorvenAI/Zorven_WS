'use client';

import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { FileUploadManager } from '@/components/files/FileUploadManager';

export default function FilesPage() {
  // Protect this route - redirects to login if not authenticated
  useAuth();
  const { canEdit } = useTenantRole();

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-dark via-brand-dark to-brand-purple/20">
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <Link
          href="/dashboard"
          className="inline-flex items-center text-sm text-brand-silver/70 hover:text-brand-electric mb-6 transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          <span>Back to Dashboard</span>
        </Link>

        {/* Main Content Card */}
        <div className="glass-card p-8">
          <div className="mb-8">
            <h1 className="font-heading text-3xl font-heading font-bold text-white mb-2">
              📁 Brand Assets
            </h1>
            <p className="text-brand-silver/70 font-body">
              Upload and manage your brand files. Files are automatically processed
              through our AI pipeline for indexing and analysis.
            </p>
          </div>

          {/* Pipeline Info Banner */}
          <div className="mb-6 p-4 bg-brand-electric/10 border border-brand-electric/30 rounded-lg">
            <h3 className="font-heading text-sm font-medium text-brand-electric mb-2">
              🚀 Automatic Processing Pipeline
            </h3>
            <div className="flex flex-wrap gap-4 text-xs text-brand-silver/70">
              <span className="flex items-center gap-1">
                <span className="text-yellow-400">🕐</span> Pending
              </span>
              <span>→</span>
              <span className="flex items-center gap-1">
                <span className="text-blue-400">📥</span> Ingested
              </span>
              <span>→</span>
              <span className="flex items-center gap-1">
                <span className="text-purple-400">✨</span> Curated
              </span>
              <span>→</span>
              <span className="flex items-center gap-1">
                <span className="text-green-400">✅</span> Indexed
              </span>
            </div>
            <p className="text-xs text-brand-silver/50 mt-2">
              Once indexed, your assets are available for AI-powered brand insights.
            </p>
          </div>

          {/* File Upload Manager */}
          <FileUploadManager canEdit={canEdit} />
        </div>

        {/* Help Section */}
        <div className="mt-6 text-center">
          <p className="text-sm text-brand-silver/50">
            Supported formats: Images (JPG, PNG, GIF, WebP), Videos (MP4, MOV), Documents (PDF, DOC, DOCX)
          </p>
          <p className="text-sm text-brand-silver/50 mt-1">
            Maximum file size: 50MB per file
          </p>
        </div>
      </div>
    </div>
  );
}
