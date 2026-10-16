/**
 * Contact List Service for Agile Sales & Marketing.
 * Manages static lead/contact lists, membership dual-pointers,
 * unresolved email warnings, and campaign synchronization.
 */

export interface ContactListItem {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  type: string;
  member_count: number;
  campaigns_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssociatedCampaignItem {
  id: string;
  name: string;
  status: string;
  type: string;
  associated_at: string;
}

export interface ContactListDetail extends ContactListItem {
  valid_email_count: number;
  unresolved_email_count: number;
  associated_campaigns: AssociatedCampaignItem[];
  outreach_sent: number;
  outreach_delivered: number;
  outreach_replied: number;
  outreach_bounced: number;
  meetings_booked: number;
}

export interface ContactListMember {
  id: string;
  contact_id?: string | null;
  lead_id?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  job_title?: string | null;
  source?: string | null;
  has_valid_email: boolean;
  is_unresolved_email: boolean;
  added_at: string;
}

export interface ContactListCatalogResult {
  items: ContactListItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface ContactListMembersResult {
  items: ContactListMember[];
  total: number;
  skip: number;
  limit: number;
}

export interface ContactListCreateInput {
  name: string;
  description?: string;
  type?: string;
}

export interface ContactListUpdateInput {
  name?: string;
  description?: string;
}

export interface AddMembersResponse {
  list_id: string;
  added_count: number;
  already_members_count: number;
  failed_count: number;
  added_member_ids: string[];
  errors: string[];
}

export interface CampaignListAttachResult {
  campaign_id: string;
  contact_list_id: string;
  newly_enrolled_count: number;
  already_enrolled_count: number;
  unresolved_email_count: number;
  suppressed_opt_out_count: number;
  unresolved_members: Array<{ id: string; name: string; email?: string | null; reason: string }>;
}

export interface CampaignListSyncResult {
  campaign_id: string;
  contact_list_id: string;
  newly_enrolled_count: number;
  already_enrolled_count: number;
  unresolved_email_count: number;
  suppressed_opt_out_count: number;
  unresolved_members: Array<{ id: string; name: string; email?: string | null; reason: string }>;
}

/**
 * Fetch all contact lists for the organization.
 */
export async function fetchContactLists(options?: {
  search?: string;
  listType?: string;
  skip?: number;
  limit?: number;
}): Promise<ContactListCatalogResult> {
  const params = new URLSearchParams();
  if (options?.search?.trim()) params.append("search", options.search.trim());
  if (options?.listType && options.listType.toLowerCase() !== "all") {
    params.append("list_type", options.listType);
  }
  if (options?.skip !== undefined) params.append("skip", String(options.skip));
  if (options?.limit !== undefined) params.append("limit", String(options.limit));

  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/lists${qs}`, { cache: "no-store" });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to fetch lists (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Trigger safe source-list synchronization for the organization.
 */
export async function syncSourceLists(): Promise<{
  synced_lists: Array<{ list_id: string; name: string; type: string; matching_leads_count: number; newly_added_count: number; already_members_count: number }>;
  total_lists_synced: number;
  total_new_memberships: number;
}> {
  const res = await fetch(`/api/lists/sync-sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to sync source lists (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Fetch a single contact list detail by ID.
 */
export async function getContactList(listId: string): Promise<ContactListDetail> {
  const res = await fetch(`/api/lists/${listId}`, { cache: "no-store" });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to fetch list ${listId} (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Create a new named contact list.
 */
export async function createContactList(data: ContactListCreateInput): Promise<ContactListItem> {
  const res = await fetch(`/api/lists`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: data.name,
      description: data.description || null,
      type: data.type || "static",
    }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to create list (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Update list name or description.
 */
export async function updateContactList(
  listId: string,
  data: ContactListUpdateInput
): Promise<ContactListItem> {
  const res = await fetch(`/api/lists/${listId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to update list (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Delete a contact list while preserving underlying CRM records.
 */
export async function deleteContactList(listId: string): Promise<void> {
  const res = await fetch(`/api/lists/${listId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to delete list (HTTP ${res.status})`);
  }
}

/**
 * Fetch members of a contact list with pagination, search, and email status filters.
 */
export async function fetchContactListMembers(
  listId: string,
  options?: {
    search?: string;
    has_unresolved_email?: boolean;
    skip?: number;
    limit?: number;
  }
): Promise<ContactListMembersResult> {
  const params = new URLSearchParams();
  if (options?.search?.trim()) params.append("search", options.search.trim());
  if (options?.has_unresolved_email !== undefined) {
    params.append("has_unresolved_email", String(options.has_unresolved_email));
  }
  if (options?.skip !== undefined) params.append("skip", String(options.skip));
  if (options?.limit !== undefined) params.append("limit", String(options.limit));

  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/lists/${listId}/members${qs}`, { cache: "no-store" });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to fetch members (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Add CRM contacts and/or raw leads to a list.
 */
export async function addMembersToList(
  listId: string,
  data: { contactIds?: string[]; leadIds?: string[] }
): Promise<AddMembersResponse> {
  const res = await fetch(`/api/lists/${listId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contact_ids: data.contactIds || [],
      lead_ids: data.leadIds || [],
    }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to add members (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Remove a member from a list without deleting the underlying CRM contact/lead.
 */
export async function removeMemberFromList(listId: string, memberId: string): Promise<void> {
  const res = await fetch(`/api/lists/${listId}/members/${memberId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to remove member (HTTP ${res.status})`);
  }
}

/**
 * Fetch lists attached to a campaign.
 */
export async function fetchCampaignAttachedLists(campaignId: string): Promise<ContactListItem[]> {
  const res = await fetch(`/api/campaigns/${campaignId}/lists`, { cache: "no-store" });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to fetch campaign lists (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Attach a list to a campaign.
 */
export async function attachListToCampaign(
  campaignId: string,
  contactListId: string,
  syncImmediately: boolean = true
): Promise<CampaignListAttachResult> {
  const res = await fetch(`/api/campaigns/${campaignId}/lists`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contact_list_id: contactListId,
      sync_immediately: syncImmediately,
    }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to attach list to campaign (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Detach a list from a campaign without deleting campaign contacts.
 */
export async function detachListFromCampaign(campaignId: string, contactListId: string): Promise<void> {
  const res = await fetch(`/api/campaigns/${campaignId}/lists/${contactListId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to detach list (HTTP ${res.status})`);
  }
}

/**
 * Explicitly synchronize newly added members from a list into a campaign.
 */
export async function syncCampaignList(
  campaignId: string,
  contactListId: string
): Promise<CampaignListSyncResult> {
  const res = await fetch(`/api/campaigns/${campaignId}/lists/${contactListId}/sync`, {
    method: "POST",
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error || `Failed to sync list (HTTP ${res.status})`);
  }
  return res.json();
}
