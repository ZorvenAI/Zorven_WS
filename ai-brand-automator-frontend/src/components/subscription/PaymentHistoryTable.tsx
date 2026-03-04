'use client';

import { PaymentHistory } from '@/lib/api';

interface PaymentHistoryTableProps {
  payments: PaymentHistory[];
  isLoading?: boolean;
}

export function PaymentHistoryTable({
  payments,
  isLoading,
}: PaymentHistoryTableProps) {
  const statusColors: Record<string, string> = {
    succeeded: 'bg-brand-mint/20 text-brand-mint',
    pending: 'bg-yellow-500/20 text-yellow-400',
    failed: 'bg-red-500/20 text-red-400',
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatAmount = (amount: string, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(parseFloat(amount));
  };

  if (isLoading) {
    return (
      <div className="glass-card p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-1/4 rounded bg-white/10" />
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded bg-white/5" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (payments.length === 0) {
    return (
      <div className="glass-card p-6">
        <div className="text-center">
          <svg
            className="mx-auto h-12 w-12 text-brand-silver/50"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <h3 className="mt-4 text-lg font-heading font-medium text-white">
            No Payment History
          </h3>
          <p className="mt-2 text-sm text-brand-silver/70 font-body">
            Your payment history will appear here once you subscribe.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="border-b border-white/10 px-6 py-4">
        <h3 className="text-lg font-heading font-semibold text-white">Payment History</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-white/10">
          <thead className="bg-white/5">
            <tr>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-brand-silver/70"
              >
                Date
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-brand-silver/70"
              >
                Description
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-brand-silver/70"
              >
                Amount
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-brand-silver/70"
              >
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {payments.map((payment) => (
              <tr key={payment.id} className="hover:bg-white/5 transition-colors">
                <td className="whitespace-nowrap px-6 py-4 text-sm text-white">
                  {formatDate(payment.created_at)}
                </td>
                <td className="px-6 py-4 text-sm text-brand-silver/70">
                  {payment.description || 'Subscription payment'}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-white">
                  {formatAmount(payment.amount, payment.currency)}
                </td>
                <td className="whitespace-nowrap px-6 py-4">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      statusColors[payment.status] || 'bg-white/10 text-brand-silver'
                    }`}
                  >
                    {payment.status.charAt(0).toUpperCase() +
                      payment.status.slice(1)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
