'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-brand-midnight text-brand-silver">
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-2xl p-8">
            <div className="flex items-center justify-center w-12 h-12 mx-auto bg-red-500/20 rounded-full">
              <svg
                className="w-6 h-6 text-red-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h2 className="mt-4 text-xl font-semibold text-white text-center">
              Something went wrong
            </h2>
            <p className="mt-2 text-sm text-gray-400 text-center">
              We&apos;re sorry, but something unexpected happened. Please try
              refreshing the page.
            </p>
            {process.env.NODE_ENV === 'development' && error && (
              <details className="mt-4 text-xs text-gray-300 bg-white/5 p-3 rounded-lg border border-white/10">
                <summary className="cursor-pointer font-medium">
                  Error details
                </summary>
                <pre className="mt-2 whitespace-pre-wrap text-red-300">
                  {error.message}
                </pre>
              </details>
            )}
            <div className="mt-6 flex gap-3">
              <button
                onClick={reset}
                className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors"
              >
                Try Again
              </button>
              <button
                onClick={() => (window.location.href = '/dashboard')}
                className="flex-1 px-4 py-2 text-sm font-medium text-gray-300 bg-white/10 hover:bg-white/15 rounded-lg transition-colors"
              >
                Go to Dashboard
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
