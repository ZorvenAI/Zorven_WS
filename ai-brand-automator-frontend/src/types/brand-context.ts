export interface BrandContextEntry {
  /** 'parent' | 'sub_brand:<slug>' | 'product_line:<slug>' | 'endorsed:<slug>' */
  brand_context_id: string;
  /** Display name, e.g. 'Acme Pro' */
  name: string;
  /** 'parent' | 'sub_brand' | 'product_line' | 'endorsed' */
  brand_scope: string;
  /** Parent brand name, e.g. 'Acme Corp' */
  parent_brand: string;
  /** Relationship to parent, e.g. 'branded_house' */
  relationship_to_parent: string;
  /** Target persona/audience (may be null) */
  target_persona: string | null;
  /** Industry vertical */
  industry?: string;
}
