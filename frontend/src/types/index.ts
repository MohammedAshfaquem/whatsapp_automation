export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  is_staff: boolean;
  is_superuser: boolean;
  platform_role?: string;
  is_platform_operator?: boolean;
  email_verified: boolean;
}

export interface Tenant {
  meta_setup_required?: boolean;
  meta_setup_ready?: boolean;
  meta_setup_reason?: string;
  whatsapp_number?: string;
  id: number;
  name: string;
  slug: string;
  plan: string;
  plan_name: string;
  subscription_status: string;
  is_active: boolean;
  logo_url?: string;
  timezone?: string;
  contact_email?: string;
  contact_phone?: string;
}

export interface Membership {
  role: 'OWNER' | 'ADMIN' | 'STAFF' | 'SUPERUSER';
  role_display: string;
  is_admin: boolean;
  is_owner: boolean;
}

export interface UserTenant {
  id: number;
  name: string;
  slug: string;
  role: string;
  role_display: string;
}

export interface CapabilityItem {
  allowed: boolean;
  reason: string;
}

export interface CapabilitiesMap {
  [key: string]: CapabilityItem;
}

export interface QuotaMetric {
  sent?: number;
  allowance?: number;
  remaining?: number;
  percent?: number;
  count?: number;
  limit?: number;
}

export interface UsageData {
  messages: QuotaMetric;
  documents: QuotaMetric;
  contacts: QuotaMetric;
  staff: QuotaMetric;
}

export interface BootstrapResponse {
  user: User;
  tenant: Tenant | null;
  membership: Membership | null;
  user_tenants: UserTenant[];
  is_inspecting: boolean;
  capabilities: CapabilitiesMap;
  usage: UsageData | null;
}

export interface Contact {
  id: number;
  name: string;
  phone_number: string;
  email: string;
  company?: { id: number; name: string } | null;
  owner?: { id: number; name: string; username: string } | null;
  lifecycle_stage: string;
  lifecycle_status?: string;
  tags?: string[];
  custom_fields?: Record<string, string>;
  notes?: string;
  lead_score: number;
  created_at: string;
  updated_at?: string;
}

export interface TimelineEvent {
  event_type: string;
  event_type_display?: string;
  text?: string;
  details?: string;
  date: string;
  created_at?: string;
}

export interface TimelinePage {
  items: TimelineEvent[];
  total_count: number;
  total_pages: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ContactNoteItem {
  id: number;
  content: string;
  created_at: string;
  author__username?: string;
}

export interface ContactDealItem {
  id: number;
  title: string;
  amount: number;
  value: number;
  currency: string;
  stage_name: string;
  is_won: boolean;
  is_lost: boolean;
  status: string;
}

export interface ContactActivityItem {
  id: number;
  title: string;
  activity_type: string;
  activity_type_display?: string;
  status: string;
  priority: string;
  due_date?: string | null;
  is_overdue?: boolean;
  assigned_to?: string | null;
}

export interface ContactDetailResponse {
  contact: Contact;
  timeline?: TimelinePage | TimelineEvent[];
  timeline_items?: TimelineEvent[];
  notes?: ContactNoteItem[];
  deals?: ContactDealItem[];
  activities?: ContactActivityItem[];
}

export interface Company {
  id: number;
  name: string;
  domain: string;
  industry: string;
  contact_count: number;
  deal_count: number;
}

export interface Deal {
  id: number;
  title: string;
  value: string;
  currency: string;
  customer_name?: string | null;
  customer_phone?: string | null;
  assigned_to?: string | null;
  expected_close_date?: string | null;
  win_probability: number;
  status: string;
}

export interface DealStageData {
  id: number;
  name: string;
  order: number;
  win_probability: number;
  is_won: boolean;
  is_lost: boolean;
  deals: Deal[];
  deal_count: number;
  total_value: string;
}

export interface Activity {
  id: number;
  title: string;
  activity_type: string;
  activity_type_display: string;
  status: 'PENDING' | 'COMPLETED' | 'CANCELLED';
  priority: 'LOW' | 'MEDIUM' | 'HIGH';
  due_date?: string | null;
  is_overdue: boolean;
  customer_name?: string | null;
  customer_phone?: string | null;
  assigned_to?: string | null;
}

export interface Conversation {
  id: number;
  customer_id?: number | null;
  customer_name: string;
  customer_phone: string;
  channel: string;
  channel_display: string;
  service_name: string;
  status: string;
  status_display: string;
  last_message_text: string;
  last_message_direction?: 'INBOUND' | 'OUTBOUND';
  last_message_at?: string | null;
  assigned_staff?: string | null;
  assigned_staff_id?: number | null;
  unread_count?: number;
  handover_required: boolean;
  handoff_summary?: string;
  is_window_open?: boolean;
}

export interface MessageItem {
  id: number;
  direction: 'INBOUND' | 'OUTBOUND';
  sender_type: string;
  author_name?: string;
  text: string;
  status: string;
  delivery_status?: 'PENDING' | 'SENDING' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED' | 'BLOCKED' | null;
  delivery_error?: string | null;
  delivery_id?: number | null;
  media_type?: string;
  media_name?: string;
  media_mime?: string;
  media_size?: number;
  media_url?: string;
  timestamp: string;
}

export interface WhatsAppTemplateItem {
  id: number;
  name: string;
  category: string;
  language: string;
  body_text: string;
  variables: string[];
  status: string;
}

export interface WhatsAppBusinessProfileData {
  about: string;
  description: string;
  address: string;
  email: string;
  websites: string[];
  vertical: string;
  profile_picture_url?: string;
}

export interface WhatsAppMetaInfo {
  verified_name: string;
  display_phone_number: string;
  quality_rating: string;
  messaging_limit_tier: string;
  code_verification_status: string;
  is_live: boolean;
}

export interface Booking {
  id: number;
  customer_name: string;
  customer_phone: string;
  service_name: string;
  preferred_date?: string | null;
  preferred_time?: string;
  address?: string;
  status: string;
  status_display: string;
  created_at: string;
}

export interface Service {
  id: number;
  name: string;
  category: string;
  price_type: string;
  price_type_display: string;
  price_amount?: string | null;
  currency: string;
  contact_number: string;
  description: string;
  is_active: boolean;
}

export interface FAQ {
  id: number;
  category: string;
  question: string;
  answer: string;
  is_active: boolean;
  created_at: string;
}

export interface KnowledgeDocument {
  id: number;
  category: string;
  title: string;
  content: string;
  is_active: boolean;
  created_at: string;
}

export interface TeamMember {
  id: number;
  user_id: number;
  username: string;
  full_name: string;
  email: string;
  role: 'OWNER' | 'ADMIN' | 'STAFF';
  role_display: string;
  is_active: boolean;
  joined_at: string;
}

export interface Invitation {
  id: number;
  email: string;
  role: string;
  role_display: string;
  is_expired: boolean;
  created_at: string;
  token: string;
}
