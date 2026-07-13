export interface ApiMeta {
  request_id: string;
  timestamp: string;
}

export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: PaginationMeta;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id: string;
    details: Array<{ location: Array<string | number>; message: string; type: string }>;
  };
  meta: ApiMeta;
}

export interface AdminPrincipal {
  user_id: string;
  tenant_id: string;
  allowed_store_ids: string[];
  roles: string[];
  permissions: string[];
  session_id: string | null;
  auth_method: 'session' | 'legacy_token';
}
