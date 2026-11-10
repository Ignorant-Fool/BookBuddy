/** 小工具：时间、字数、错误文案。 */

export function clockNow(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function errorMessage(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object') {
    const anyErr = err as any;
    const detail = anyErr?.response?.data?.error;
    if (typeof detail === 'string' && detail) return detail;
    if (typeof anyErr?.message === 'string') return anyErr.message;
  }
  return '未知错误';
}

export function formatChars(chars: number): string {
  if (chars >= 10000) return `${(chars / 10000).toFixed(1)} 万字`;
  return `${chars} 字`;
}

/** 去掉模型偶尔加在开头的冗余一级标题，让气泡更干净。 */
export function tidyAnswer(text: string): string {
  return (text || '').replace(/^\s*#{1,2}\s+.*\n+/, (m) => (/^\s*#\s*/.test(m) ? m.replace(/^\s*#\s*/, '') : m));
}
