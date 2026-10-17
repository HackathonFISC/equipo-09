import { UserRoundPlus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { OpportunityList } from "@/components/opportunity-list";
import { PageShell, RoleHeader } from "@/components/page-shell";

export const metadata: Metadata = { title: "Mis oportunidades" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function OportunidadesPage({
	searchParams,
}: {
	searchParams: Promise<{ id?: string | string[] }>;
}) {
	const { id } = await searchParams;
	const youthId = typeof id === "string" && UUID.test(id) ? id : null;

	return (
		<PageShell width="narrow">
			<RoleHeader
				title="Mis oportunidades"
				description="Solo ofertas a las que puedes llegar. Cada una dice cuánto tardas, cuánto gastas y por qué encajas; ninguna se envía sin que un orientador la revise."
			/>
			{youthId ? (
				<OpportunityList key={youthId} youthId={youthId} />
			) : (
				<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
					<UserRoundPlus
						className="size-8 text-muted-foreground"
						aria-hidden="true"
					/>
					<p className="font-medium">No encontramos qué perfil abrir</p>
					<p className="max-w-xs text-muted-foreground text-sm">
						Regístrate primero; al terminar te traemos aquí.
					</p>
					<Link
						href="/joven/registro"
						className="text-primary text-sm underline underline-offset-4"
					>
						Ir al registro
					</Link>
				</div>
			)}
		</PageShell>
	);
}
