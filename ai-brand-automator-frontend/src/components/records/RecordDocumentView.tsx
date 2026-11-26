/**
 * The frozen content of a meeting record, as a reader sees it on screen.
 *
 * Shared by the agency's Documents tab and the public signing page, so the
 * person preparing a record and the person signing it read the same thing.
 */

import type { RecordDocument } from '@/lib/meeting-records';

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return 'Time not recorded';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function Bold({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*.+?\*\*)/g).map((part, index) =>
        part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
          <strong key={index} className="text-white">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-white/60">
      {children}
    </h4>
  );
}

export interface RecordDocumentViewProps {
  document: RecordDocument;
  /** The signing page shows everything; the tab's preview leaves some out. */
  full?: boolean;
}

export default function RecordDocumentView({
  document: doc,
  full = false,
}: RecordDocumentViewProps) {
  const client = doc.parties.client;
  return (
    <div className="space-y-5 text-sm text-brand-silver">
      <section>
        <Heading>Parties</Heading>
        <p>
          <span className="text-white">{doc.parties.agency.name || '—'}</span> and{' '}
          <span className="text-white">{client.legal_name || client.name || '—'}</span>
        </p>
        {full && client.registered_address && <p>{client.registered_address}</p>}
        {!full && (
          <p>
            Signing for the client: {client.signatory_name || '—'}
            {client.signatory_title ? `, ${client.signatory_title}` : ''}
            {client.signatory_email ? ` (${client.signatory_email})` : ''}
          </p>
        )}
      </section>

      {full && (
        <section>
          <Heading>Meeting</Heading>
          <p>{formatWhen(doc.meeting.started_at)}</p>
          {doc.attendees.length > 0 && (
            <p>
              Attended by{' '}
              {doc.attendees
                .map((a) => (a.role ? `${a.name} (${a.role})` : a.name))
                .join(', ')}
            </p>
          )}
          {doc.completeness.note && <p className="mt-1">{doc.completeness.note}</p>}
        </section>
      )}

      <section>
        <Heading>Agreements</Heading>
        {doc.agreements.preamble && full && (
          <p className="mb-2 whitespace-pre-line">{doc.agreements.preamble}</p>
        )}
        {doc.agreements.items.length === 0 ? (
          <p>No agreements were recorded in this meeting.</p>
        ) : (
          <ol className="space-y-1.5" aria-label="Agreements">
            {doc.agreements.items.map((item) => (
              <li key={item.number} className="flex gap-3">
                <span className="shrink-0 font-semibold text-white">{item.number}</span>
                <span className="whitespace-pre-line">
                  <Bold text={item.text} />
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {full && doc.description && (
        <section>
          <Heading>Description</Heading>
          <p className="whitespace-pre-line">
            <Bold text={doc.description} />
          </p>
        </section>
      )}

      <section>
        <Heading>Clean transcript ({doc.transcript.length} lines)</Heading>
        {doc.transcript.length === 0 ? (
          <p>No clean transcript is available for this meeting.</p>
        ) : (
          <ol
            className="max-h-72 space-y-1 overflow-y-auto rounded-lg bg-white/5 p-3"
            aria-label="Transcript"
          >
            {doc.transcript.map((line, index) => (
              <li key={index} className="flex gap-3">
                <span className="w-7 shrink-0 text-right text-xs text-white/40">
                  {index + 1}
                </span>
                <span className="break-words">{line}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {full ? (
        <section>
          <Heading>Legal status</Heading>
          <p className="whitespace-pre-line text-xs">{doc.clause.text}</p>
        </section>
      ) : (
        <p className="text-xs">
          The PDF also carries the description, attendance, recording consent and
          the legal status clause.
        </p>
      )}
    </div>
  );
}
