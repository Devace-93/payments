/** Wire shapes from CONTRACT.md → Objects / Session / Me. */

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  handle: string;
  name: string | null;
  avatar_url: string;
  created_at: string;
}

export type Provider = "google" | "github" | "discord";

export interface Identity {
  provider: Provider;
  provider_email: string | null;
  created_at: string;
}

export interface Me {
  user: User;
  has_password: boolean;
  identities: Identity[];
}

export interface SessionInfo {
  id: string;
  expires_at: string;
}

export interface SessionResponse {
  user: User;
  session: SessionInfo;
}

export interface SessionRow {
  id: string;
  current: boolean;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  [key: string]: unknown;
}
