'use client';

import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  editProvenance,
  getSessionProvenance,
  type FieldProvenanceRow,
} from '@/lib/onboarding-sessions';

interface UseWizardProvenanceResult {
  provenanceMap: Map<string, FieldProvenanceRow>;
  loading: boolean;
  editField: (fieldName: string, newValue: unknown) => Promise<void>;
  sessionId: string | null;
  stepPath: (path: string) => string;
}

export function useWizardProvenance(page: number): UseWizardProvenanceResult {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('sessionId');

  const [provenanceMap, setProvenanceMap] = useState<
    Map<string, FieldProvenanceRow>
  >(new Map());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    const fetchProvenance = async () => {
      setLoading(true);
      try {
        const data = await getSessionProvenance(sessionId);
        if (cancelled) return;

        const map = new Map<string, FieldProvenanceRow>();
        for (const group of data.groups) {
          if (group.page === page) {
            for (const row of group.fields) {
              map.set(row.field_name, row);
            }
          }
        }
        setProvenanceMap(map);
      } catch {
        if (!cancelled) setProvenanceMap(new Map());
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchProvenance();
    return () => {
      cancelled = true;
    };
  }, [sessionId, page]);

  const editField = useCallback(
    async (fieldName: string, newValue: unknown) => {
      const row = provenanceMap.get(fieldName);
      if (!row) return;
      await editProvenance(row.id, newValue);
    },
    [provenanceMap],
  );

  const stepPath = useCallback(
    (path: string) => (sessionId ? `${path}?sessionId=${sessionId}` : path),
    [sessionId],
  );

  return { provenanceMap, loading, editField, sessionId, stepPath };
}
