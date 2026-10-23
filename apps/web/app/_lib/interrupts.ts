// Sổ interrupt đang chờ của client AG-UI. Graph chỉ chờ một interrupt mỗi lúc, nên trước khi
// resume chỉ giữ đúng interrupt đang trả lời; interrupt cũ còn sót (vd bấm duyệt hai lần) bị bỏ.
export function keepPending<T extends { id: string }>(list: T[], interruptId: string): T[] {
  return list.filter((i) => i.id === interruptId);
}
