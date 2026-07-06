export type LanguageCode = "zh" | "en" | string;

export interface MenuItem {
  id: string;
  name?: string;
  name_en?: string;
  price?: number | string;
  category?: string;
  image?: string;
  emoji?: string;
  description?: string;
  push_text?: string;
  quantity?: number;
  count?: number;
}

export interface CartItem extends MenuItem {
  id: string;
  quantity: number;
}

export interface CartAction {
  action?: string;
  id?: string;
  quantity?: number | string;
}

export interface MenuVisual {
  image: string;
  emoji: string;
}

export interface InteractionEventPayload {
  [key: string]: unknown;
}

export interface VoiceStreamAudioChunk {
  type: "audio";
  data: string;
  format?: string;
}

export interface VoiceStreamDoneChunk {
  type: "done";
  status?: string;
  [key: string]: unknown;
}

export type VoiceStreamChunk = VoiceStreamAudioChunk | VoiceStreamDoneChunk;

export interface VoiceStreamHandlers {
  onAudio: (base64Audio: string, format: string) => void;
  onDone: (chunk: VoiceStreamChunk) => void;
  onError: (message: string) => void;
}

export interface RealtimeEvent {
  type: string;
  [key: string]: unknown;
}

export interface RealtimeHandlers {
  open?: () => void;
  close?: () => void;
  error?: (error: Event | Error) => void;
  message?: (event: RealtimeEvent) => void;
  [eventType: string]: ((event: RealtimeEvent) => void) | (() => void) | ((error: Event | Error) => void) | undefined;
}

export interface RealtimeClient {
  send: (payload?: Record<string, unknown>) => boolean;
  close: () => void;
  readonly socket: WebSocket | null;
}

export interface KioskRuntime {
  cartManager?: CartManager;
  clearAllPushCards?: () => void;
  getFeatures?: () => Record<string, unknown>;
  getKioskLang?: () => LanguageCode;
  getRuntimeSettings?: () => Record<string, unknown>;
  isAdminMode?: () => boolean;
  isKioskActive?: () => boolean;
  isKioskMode?: () => boolean;
  isPosActive?: () => boolean;
  isPosMode?: () => boolean;
  itemMatchesSubFilter?: (item: MenuItem, filter: string) => boolean;
  kt?: (key: string) => string;
  sessionId?: string;
  showPushNotice?: (text: string) => void;
  trackInteractionEvent?: (event: InteractionEventPayload) => void | Promise<unknown>;
  pausePassiveListener?: () => void;
  resumePassiveListener?: () => void;
  triggerEmotionCapture?: (eventType: string) => void;
  triggerEmotionCaptureAndWait?: (eventType: string) => Promise<void>;
}

export interface PointOfSaleRuntime extends KioskRuntime {}

export interface CartManagerOptions {
  ui: {
    cartList: HTMLElement;
    checkoutBtn: HTMLButtonElement;
    totalPrice: HTMLElement;
    cartCountBadge: HTMLElement;
  } & Record<string, HTMLElement | HTMLButtonElement | null>;
  escapeHTML: (value: unknown) => string;
  findMenuItems: (ids?: string[]) => MenuItem[];
  onCartChange?: (items: CartItem[]) => void;
  t?: (key: string) => string;
  lang?: () => LanguageCode;
  getVisual?: (item: MenuItem) => MenuVisual;
}

export interface CartManager {
  addToCart: (item: MenuItem) => void;
  addToCartByQuantity: (item: MenuItem, requestedQuantity?: number) => void;
  updateCartQty: (id: string, delta: number) => void;
  deleteCartItem: (id: string) => void;
  applyCartActions: (actions?: CartAction[]) => string[];
  renderCart: () => void;
  getCartIds: () => string[];
  getCartItems: () => CartItem[];
  getCartTotal: () => number;
  clearCart: () => void;
}
