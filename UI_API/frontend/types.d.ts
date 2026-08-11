export interface MenuItem {
  id: string;
  name?: string;
  name_en?: string;
  price?: number | string | undefined;
  category?: string;
  image?: string;
  emoji?: string;
  description?: string;
  push_text?: string;
  quantity?: number;
  count?: number;
  original_price?: number | string | undefined;
  applied_offer_id?: string | undefined;
  offer_ids?: string[] | undefined;
  promotion_title?: string | undefined;
  base_price?: number | undefined;
  effective_price?: number | undefined;
  discount?: number | undefined;
  price_conditional?: boolean | undefined;
  conditional_price?: number | undefined;
  price_condition_text?: string | undefined;
  options?: Array<{ id: string; name?: string; price?: number }> | undefined;
  decision_id?: string | undefined;
  strategy?: string | undefined;
  strategy_version?: string | undefined;
  experiment_id?: string | undefined;
  variant_id?: string | undefined;
  fallback_status?: string | undefined;
}

export interface MenuPriceProjection {
  item_id: string;
  base_price: number;
  effective_price: number;
  discount: number;
  activity_id: string;
  activity_name: string;
  conditional: boolean;
  conditional_price?: number | null;
  required_cart_item_ids: string[];
}

export interface CartQuoteLine {
  item_id: string;
  name: string;
  category: string;
  quantity: number;
  base_unit_price: number;
  effective_unit_price: number;
  option_unit_total: number;
  discount_unit_total: number;
  activity_id: string;
  activity_name: string;
}

export interface CartQuote {
  items: CartQuoteLine[];
  subtotal: number;
  option_total: number;
  discount_total: number;
  tax_total: number;
  total: number;
  currency: string;
  quote_version: string;
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

export interface VoiceStreamTranscriptChunk {
  type: "transcript";
  user_text: string;
}

export interface VoiceStreamAssistantTextChunk {
  type: "assistant_text";
  ai_response: string;
  user_text?: string;
}

export interface VoiceStreamDoneChunk {
  type: "done";
  status?: string;
  [key: string]: unknown;
}

export type VoiceStreamChunk = VoiceStreamAudioChunk | VoiceStreamTranscriptChunk | VoiceStreamAssistantTextChunk | VoiceStreamDoneChunk;

export type VoiceTurnEventType =
  | "accepted"
  | "transcribing"
  | "transcript"
  | "assistant_result"
  | "completed"
  | "transcription_failed"
  | "assistant_failed"
  | "playback_failed";

export interface VoiceTurnEventPayload {
  status?: string;
  message?: string;
  user_text?: string;
  ai_response?: string;
  audio_base64?: string;
  audio_format?: string;
  playback_status?: string;
  playback_message?: string;
  order_draft?: unknown;
  mentioned_ids?: string[];
  dialogue?: unknown;
  [key: string]: unknown;
}

export interface VoiceTurnEvent {
  voice_turn_id: string;
  sequence: number;
  type: VoiceTurnEventType;
  payload: VoiceTurnEventPayload;
  terminal: boolean;
}

export interface VoiceTurnEventCandidate {
  voice_turn_id: unknown;
  sequence: unknown;
  type: unknown;
  payload: unknown;
  terminal: unknown;
}

export interface VoiceTurnProtocolState {
  voiceTurnId: string;
  lastAcknowledgedSequence: number;
  terminal: boolean;
  signatures: Map<number, string>;
}

export interface VoiceStreamHandlers {
  onAudio: (base64Audio: string, format: string) => void;
  onEvent?: (event: VoiceTurnEventCandidate) => void;
  onTranscript?: (payload: VoiceTurnEventPayload) => void;
  onAssistantText?: (payload: VoiceTurnEventPayload) => void;
  onDone: (payload: VoiceTurnEventPayload) => void;
  /** `refusal` carries the service's own reason when it declined the turn. */
  onError: (message: string, refusal?: { status: number; code: string }) => void;
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
  getRuntimeSettings?: () => Record<string, unknown>;
  isAdminMode?: () => boolean;
  isKioskActive?: () => boolean;
  isKioskMode?: () => boolean;
  isPosActive?: () => boolean;
  isPosMode?: () => boolean;
  itemMatchesSubFilter?: (item: MenuItem, filter: string) => boolean;
  kioskText?: (key: string) => string;
  sessionId?: string;
  showPushNotice?: (text: string) => void;
  trackInteractionEvent?: (event: InteractionEventPayload) => void | Promise<unknown>;
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
  onCartChange?: (items: CartItem[], reason?: "cart_change" | "quote_applied" | "quote_pending" | "quote_failed") => void;
  t?: (key: string) => string;
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
  markQuotePending: () => void;
  markQuoteFailed: () => void;
  applyServerQuote: (quote: CartQuote) => void;
  getQuoteState: () => { status: "idle" | "pending" | "ready" | "failed"; total: number | null; version: string };
}
