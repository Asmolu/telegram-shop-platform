export type LookEditorMode = 'create' | 'edit';

export function applyGeneratedLookSlug({
  mode,
  currentSlug,
  generatedSlug,
  wasManuallyEdited,
}: {
  mode: LookEditorMode;
  currentSlug: string;
  generatedSlug: string | null | undefined;
  wasManuallyEdited: boolean;
}) {
  const nextSlug = generatedSlug?.trim() ?? '';
  if (mode !== 'create' || wasManuallyEdited || currentSlug.trim() || !nextSlug) {
    return currentSlug;
  }

  return nextSlug;
}
