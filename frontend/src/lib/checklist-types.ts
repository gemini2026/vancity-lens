export type ChecklistCategory =
  | "title_legal"
  | "zoning_planning"
  | "physical"
  | "financial"
  | "municipal";

export interface ChecklistItem {
  id: string;
  label: string;
  category: ChecklistCategory;
  checked: boolean;
  notes?: string;
  createdAt: string;
}

export const DEFAULT_CHECKLIST_ITEMS: Omit<ChecklistItem, "id" | "createdAt">[] = [
  {
    label: "Title search",
    category: "title_legal",
    checked: false,
  },
  {
    label: "Encumbrances check",
    category: "title_legal",
    checked: false,
  },
  {
    label: "Legal non-conforming status",
    category: "title_legal",
    checked: false,
  },
  {
    label: "Covenant review",
    category: "title_legal",
    checked: false,
  },
  {
    label: "Current zoning verification",
    category: "zoning_planning",
    checked: false,
  },
  {
    label: "OCP designation check",
    category: "zoning_planning",
    checked: false,
  },
  {
    label: "Transit proximity confirmed",
    category: "zoning_planning",
    checked: false,
  },
  {
    label: "View cone analysis",
    category: "zoning_planning",
    checked: false,
  },
  {
    label: "Environmental site assessment (Phase 1)",
    category: "physical",
    checked: false,
  },
  {
    label: "Geotechnical report",
    category: "physical",
    checked: false,
  },
  {
    label: "Building condition assessment",
    category: "physical",
    checked: false,
  },
  {
    label: "Survey/legal plan",
    category: "physical",
    checked: false,
  },
  {
    label: "Market comparable analysis",
    category: "financial",
    checked: false,
  },
  {
    label: "Pro forma review",
    category: "financial",
    checked: false,
  },
  {
    label: "Construction cost estimate",
    category: "financial",
    checked: false,
  },
  {
    label: "Financing pre-approval",
    category: "financial",
    checked: false,
  },
  {
    label: "Development permit pre-application",
    category: "municipal",
    checked: false,
  },
  {
    label: "Utility capacity check",
    category: "municipal",
    checked: false,
  },
  {
    label: "Community amenity contribution estimate",
    category: "municipal",
    checked: false,
  },
  {
    label: "DCL estimate",
    category: "municipal",
    checked: false,
  },
];

export const CATEGORY_LABELS: Record<ChecklistCategory, string> = {
  title_legal: "Title & Legal",
  zoning_planning: "Zoning & Planning",
  physical: "Physical",
  financial: "Financial",
  municipal: "Municipal",
};
