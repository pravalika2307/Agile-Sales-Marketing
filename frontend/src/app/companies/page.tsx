import { redirect } from "next/navigation";

export default function CompaniesPage() {
  // Redundant standalone page removed per Kunal's workflow.
  // Company information is integrated into Leads and Contact List details.
  redirect("/leads");
}
