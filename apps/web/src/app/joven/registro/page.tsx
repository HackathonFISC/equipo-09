import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { DataSourceNote, ErrorState } from "@/components/data-states";
import { PageShell, RoleHeader } from "@/components/page-shell";
import { YouthRegisterForm } from "@/components/youth-register-form";
import { loadLocations } from "@/lib/api/catalog";

export const metadata: Metadata = { title: "Registro" };

export default async function RegistroPage() {
	await connection();
	const locations = await loadLocations();

	return (
		<PageShell width="narrow">
			<RoleHeader
				title="Cuéntanos cómo te mueves"
				description="Con esto calculamos cuánto tardas y cuánto gastas en llegar a cada trabajo. Solo te mostramos ofertas que te convienen."
			/>
			{locations.ok ? (
				<>
					{locations.source === "mock" ? (
						<DataSourceNote source="mock" reason={locations.reason} />
					) : null}
					<YouthRegisterForm locations={locations.data} />
				</>
			) : (
				<ErrorState
					title="No pudimos cargar los corregimientos"
					message={locations.message}
				/>
			)}
			<p className="text-center text-muted-foreground text-sm">
				<Link href="/joven" className="underline underline-offset-4">
					Volver
				</Link>
			</p>
		</PageShell>
	);
}
