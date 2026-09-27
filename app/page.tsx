import { Monitor } from "@/components/monitor";
import { loadDashboard, loadQuotes } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export default async function Page() {
  const [quotes, dashboard] = await Promise.all([loadQuotes(), loadDashboard()]);
  return <Monitor quotes={quotes} dashboard={dashboard} />;
}
