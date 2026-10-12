export function mergeEditedRecord<T extends Record<string, unknown>>(
  original: T,
  edited: Partial<T>,
): T {
  return { ...original, ...edited } as T;
}

export function mergeEditedRecords<T extends Record<string, unknown>>(
  original: T[],
  edited: Partial<T>[],
  key: keyof T = 'id' as keyof T,
): T[] {
  const byKey = new Map(edited.map((item) => [item[key], item]));
  return original.map((item) => mergeEditedRecord(item, byKey.get(item[key]) || {}));
}
