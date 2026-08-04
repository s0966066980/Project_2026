// @ts-check

/**
 * @typedef {object} KioskGroup
 * @property {string} id
 * @property {string} label
 * @property {string} labelEn
 * @property {string} image
 * @property {string[]} categories
 * @property {number} [featuredLimit]
 */

/** @type {KioskGroup[]} */
export const KIOSK_GROUPS = [
  { id: 'recommended', label: '推薦套餐', labelEn: 'Recommended Meals', image: '/static/mcd_categories/recommended.jpg', categories: ['超值全餐', '極選系列'], featuredLimit: 10 },
  { id: 'value', label: '超值全餐', labelEn: 'Value Meals', image: '/static/mcd_categories/value.jpg', categories: ['超值全餐'] },
  { id: 'premium', label: '極選系列', labelEn: 'Signature Meals', image: '/static/menu_images/MCD014.jpg', categories: ['極選系列'] },
  { id: 'side', label: '超值配餐', labelEn: 'Value Sides', image: '/static/mcd_categories/single.jpg', categories: ['超值全餐配餐'] },
  { id: 'plusone', label: '1+1星級點', labelEn: '1+1 Star Picks', image: '/static/mcd_categories/value.jpg', categories: ['1+1星級點'] },
  { id: 'sharebox', label: '分享盒', labelEn: 'Share Box', image: '/static/mcd_categories/recommended.jpg', categories: ['麥當勞分享盒'] },
  { id: 'happymeal', label: 'Happy Meal', labelEn: 'Happy Meal', image: '/static/mcd_categories/kids.jpg', categories: ['Happy Meal'] },
  { id: 'single', label: '單點餐品', labelEn: 'A La Carte', image: '/static/mcd_categories/deals.jpg', categories: ['點心'] },
  { id: 'drinks', label: '飲料甜點', labelEn: 'Drinks & Desserts', image: '/static/mcd_categories/drinks.jpg', categories: ['飲料', 'McCafé', 'McCafé'] },
  { id: 'breakfast', label: '早餐', labelEn: 'Breakfast', image: '/static/menu_images/MCD029.jpg', categories: ['早餐'] },
];

/** @type {{ [key: string]: string | Record<string, string> | undefined, filters?: Record<string, string> }} */
export const KIOSK_TEXT = {
    chooseCategory: '請選擇餐點類別',
    chooseCategorySub: '選擇分類後開始點餐',
    addHint: '點選加號加入購物車',
    searchFilter: '搜尋<br>篩選',
    home: '回首頁',
    emptyCategory: '此分類目前沒有可顯示餐點',
    addToCart: '加入購物車',
    checkoutGo: '結帳去',
    continueOrder: '繼續點餐',
    clearCart: '清空購物車',
    yourCart: '您的購物車',
    fastPayKicker: '點點卡、信用卡、掃碼支付',
    fastPayTitle: '在此快速結帳',
    counterPay: '至櫃檯排隊付款',
    backCart: '回購物車',
    cancelOrder: '取消整單訂單',
    paymentTitle: '請選擇付款方式',
    menuFallback: '目前沒有選擇任何餐點。',
    total: '總計',
    subtotal: '小計',
    secureCheckout: '安全交易 · 安心結帳',
    checkoutDone: '點餐完成！',
    thankYou: '感謝您的使用 · Thank you',
    cartCount: '共 {count} 項',
    cartEmptyTitle: '購物車是空的',
    cartEmptySub: '快去選擇喜愛的餐點吧！',
    holdVoiceOrder: '語音模式',
    voiceAskHint: '語音協助開啟後可點餐與詢問 AI 助理',
    listeningAsk: '收音中...',
    listeningOrder: '聆聽語音協助中...',
    aiThinking: 'AI 思考中...',
    recognizingOrder: '辨識餐點中...',
    priority: '優先級',
    customer: '顧客',
    addedToCart: '已加入購物車：{items}',
    noVoiceOrderItem: '沒有在菜單中找到可加入購物車的餐點。',
    networkFailed: '網路連線失敗，請稍後再試。',
    voiceOrderFailed: '語音協助失敗，請稍後再試。',
    voiceTooShort: '沒有聽到完整語音，請再說一次。',
    voiceNoSpeech: '8 秒內沒有聽到語音，請點一下再說一次。',
    voicePlaybackUnavailable: '文字結果已保留，但語音播放暫時不可用。',
    voiceMicNotReady: '麥克風尚未準備完成，請確認瀏覽器麥克風權限。',
    checkoutProcessing: '結帳中...',
    counterPayCreating: '建立櫃檯付款單...',
    counterPayDone: '請至櫃檯付款',
    filters: {
      '全部': '全部',
      '牛肉系列': '牛肉系列',
      '雞肉系列': '雞肉系列',
      '魚肉系列': '魚肉系列',
      '點心飲料': '點心飲料',
  },
};

/**
 * @param {string} key
 * @returns {string}
 */
export function kioskText(key) {
  const value = KIOSK_TEXT[key];
  return typeof value === 'string' ? value : key;
}

/**
 * @param {string} filter
 * @returns {string}
 */
export function kioskFilterLabel(filter) {
  return KIOSK_TEXT.filters?.[filter] || filter;
}

/**
 * @param {KioskGroup} group
 * @returns {string}
 */
export function kioskGroupLabel(group) {
  return group.label;
}
