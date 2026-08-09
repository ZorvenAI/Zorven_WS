"""C-04 AC-2 · an APPROVED questionnaire's questions cannot change.

In PostgreSQL, not in Python. B-05 made the same call for the provenance
grounding rule and its note is the reason: ``bulk_create`` bypasses ``save()``.
Here the hole is wider — ``queryset.update()`` and ``bulk_update()`` also skip
``save()`` and every signal that hangs off it, and both are the natural way to
renumber a set of questions. A model-level guard would be exactly the gap it
was written to close.

FR-PREP-05 asks for the approved version to be left "byte-identical". That is a
claim about every writer, including a data migration, a shell session and a
future story that has not been written yet. Only the database can make it.

The trigger allows the questionnaire's own status to move on — approving is an
UPDATE on Questionnaire, and superseding sets ``supersedes`` on the *new* row —
while freezing the Question rows an approved version owns.

**Three designs failed before this one, and the failures are the design.**

A plain BEFORE trigger covering DELETE blocked cascades: Django removes
children before the parent, so at the moment each Question goes its
questionnaire still exists and reads APPROVED. An approved questionnaire became
undeletable, which breaks M-02's erasure.

Making it DEFERRABLE INITIALLY DEFERRED fixed that and broke something worse.
The error then arrives at COMMIT, so inside a test transaction pytest.raises
never sees it and the violation surfaces in teardown instead, poisoning the
test. A rule nobody can write a test for is not a rule anyone keeps.

Having the parent announce its own deletion in a transaction-local setting
does not work either, for the same reason as the first: Django deletes the
children first, so the parent's BEFORE DELETE trigger has not fired yet when
the children need to consult the flag.

So the trigger covers **INSERT and UPDATE only**, and that is a real, stated
limitation rather than an oversight. Those are the paths an edit takes —
save(), update(), bulk_update(), and a renumber — and they are what
FR-PREP-05's "byte-identical" is actually protecting against. Deleting an
individual question out of an approved set is refused in the service layer
(see the approve/refine endpoints and their tests) but is not enforced here,
because no formulation of the check can tell that delete apart from the
cascade that erasure depends on.

If that gap ever needs closing, the way is a pre_delete signal on Questionnaire
setting the flag before Django's collector removes any children — Python
knowing something SQL cannot see. It was not worth the coupling for a path no
code takes.
"""

from django.db import migrations

FREEZE = """
CREATE OR REPLACE FUNCTION onboarding_reject_approved_question_change()
RETURNS TRIGGER AS $$
DECLARE
    parent_id bigint;
    parent_status text;
BEGIN
    parent_id := NEW.questionnaire_id;

    SELECT status INTO parent_status
    FROM onboarding_sessions_questionnaire
    WHERE id = parent_id;

    IF parent_status = 'APPROVED' THEN
        RAISE EXCEPTION
            'questionnaire % is APPROVED; its questions are frozen (C-04 AC-2). '
            'Edit it by creating the next version.',
            parent_id
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER onboarding_freeze_approved_questions
    BEFORE INSERT OR UPDATE ON onboarding_sessions_question
    FOR EACH ROW
    EXECUTE FUNCTION onboarding_reject_approved_question_change();
"""

THAW = """
DROP TRIGGER IF EXISTS onboarding_freeze_approved_questions
    ON onboarding_sessions_question;
DROP FUNCTION IF EXISTS onboarding_reject_approved_question_change();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding_sessions", "0007_questionnaire_supersedes_and_more"),
    ]

    operations = [
        # Reversible: B-01's rule for this app is that every migration is
        # additive and reversible, and a trigger that cannot be dropped would
        # strand a rollback.
        migrations.RunSQL(sql=FREEZE, reverse_sql=THAW),
    ]
