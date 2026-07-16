export const CAMPAIGN_STATUS_LABELS = Object.freeze({
  draft: '草稿', review: '待確認', scheduled: '已排程', active: '進行中',
  paused: '已暫停', ended: '已結束', archived: '已封存',
});

export const CAMPAIGN_PLACEMENT_LABELS = Object.freeze({
  menu_card: '菜單餐點卡', item_detail: '餐點詳細資料', pos_home_banner: '自助點餐機首頁活動區',
  kiosk_cart_banner: '購物車活動區', recommendation: '智慧推薦', voice: '語音優惠回答',
  ai_push: '智慧推薦提示', assist_recommend: '點餐協助推薦', choice_hesitation: '選擇協助',
  voice_assist: '語音點餐推薦', member_usual: '會員常點', global_popular: '熱門餐點',
  local_default: '門市預設', local_fallback: '門市備用推薦', recommendation_engine: '推薦排序引擎',
});

export const RECOMMENDATION_EVENT_LABELS = Object.freeze({
  recommendation_generated: '已產生推薦', recommendation_shown: '已有效曝光', recommendation_clicked: '已點擊',
  recommendation_added_to_cart: '已加入購物車', recommendation_removed_from_cart: '已從購物車移除',
  recommendation_checked_out: '已完成購買', recommendation_ignored: '未採用',
});

export const RECOMMENDATION_REASON_LABELS = Object.freeze({
  member_usual: '會員常點', global_popular: '熱門餐點', category_match: '符合偏好分類',
  promotion_match: '符合活動優惠', local_fallback: '門市備用推薦', availability_fallback: '依目前供應推薦',
});

/** @param {Record<string, string>} catalog @param {unknown} value @param {string} [fallback] */
export function zhLabel(catalog, value, fallback = '未知項目') {
  return catalog[String(value || '').trim()] || fallback;
}
