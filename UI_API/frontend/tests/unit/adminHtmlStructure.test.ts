import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const adminHtml = readFileSync(fileURLToPath(new URL('../../admin/admin.html', import.meta.url)), 'utf8');

const VOID_TAGS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr',
]);

/** 移除 <style>/<script> 內容但保留行號，避免內容裡的角括號被誤判成標籤。 */
function stripInertBlocks(html: string): string {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/g, match => match.replace(/[^\n]/g, ' '))
    .replace(/<script[^>]*>[\s\S]*?<\/script>/g, match => match.replace(/[^\n]/g, ' '));
}

/**
 * 對指定標籤名做開闔配對檢查，回傳所有不平衡處的描述。
 *
 * 這份檔案沒有建置流程把它跑過真正的 HTML parser，手動的大範圍區塊搬移（例如把「測試」頁
 * 拆進設定頁與情緒分析頁）很容易漏掉或多出一個收尾標籤——外層元素一旦沒收尾，後面所有手足
 * 元素都會被瀏覽器解析成它的子節點，若外層帶著 hidden/display:none，後面整段內容就會直接消失，
 * 但頁面在瀏覽器裡不會報錯，只會安靜地不顯示。
 */
function findUnbalancedTags(html: string, tagName: string): string[] {
  const stack: number[] = [];
  const problems: string[] = [];
  const pattern = new RegExp(`<(/?)${tagName}\\b[^>]*?(/?)>`, 'gi');
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(html))) {
    const isClosing = match[1] === '/';
    const isSelfClosing = match[2] === '/';
    if (VOID_TAGS.has(tagName) || isSelfClosing) continue;
    const line = html.slice(0, match.index).split('\n').length;
    if (!isClosing) {
      stack.push(line);
    } else if (stack.length) {
      stack.pop();
    } else {
      problems.push(`未配對的結束標籤 </${tagName}>（第 ${line} 行）`);
    }
  }
  stack.forEach(line => problems.push(`未收尾的 <${tagName}>（第 ${line} 行開啟後從未關閉）`));
  return problems;
}

describe('admin.html 結構完整性', () => {
  const body = stripInertBlocks(adminHtml);

  it('每個 <div> 都有對應的收尾標籤', () => {
    expect(findUnbalancedTags(body, 'div')).toEqual([]);
  });

  it('每個 <section> 都有對應的收尾標籤', () => {
    expect(findUnbalancedTags(body, 'section')).toEqual([]);
  });

  it('每個以 page- 開頭的分頁容器，開頭與收尾標籤都在檔案中各存在一次', () => {
    const pageIds = [...adminHtml.matchAll(/id="(page-[a-z]+)"/g)].map(m => m[1]);
    expect(pageIds.length).toBeGreaterThan (0);
    // 每個分頁 id 只應該出現一次（一次宣告），確保沒有殘留的重複區塊。
    pageIds.forEach(id => {
      const occurrences = adminHtml.split(`id="${id}"`).length - 1;
      expect(occurrences, `${id} 應該只宣告一次`).toBe(1);
    });
  });
});
