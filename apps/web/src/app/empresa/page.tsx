import { buttonVariants } from "@puente/ui/components/button";
import { cn } from "@puente/ui/lib/utils";
import { Inbox, Plus } from "lucide-react";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { DataSourceNote, ErrorState } from "@/components/data-states";
import { PageShell, RoleHeader } from "@/components/page-shell";
import { PostingIngest } from "@/components/posting-ingest";
import { PostingList, postingStatusMeta } from "@/components/posting-list";
import { loadPostings } from "@/lib/api/catalog";
import type { PostingStatus } from "@/lib/api/client";
import { mockPostings } from "@/lib/api/mocks";
import { plural } from "@/lib/format";

export const metadata: Metadata = { title: "Ofertas" };

const FILTERS = [
	"publicada",
	"bloqueada",
	"borrador",
	"cerrada",
] as const satisfies PostingStatus[];

function parseStatus(
	value: string | string[] | undefined,
): PostingStatus | undefined {
	return FILTERS.find((s) => s === value);
}

export default async function EmpresaPage({
	searchParams,
}: {
	searchParams: Promise<{ estado?: string | string[] }>;
}) {
	await connection();
	const status = parseStatus((await searchParams).estado);
	const result = await loadPostings({ status });
	// No hay "empresa actual" en el contrato: se usa la de las ofertas listadas.
	const companyId =
		(result.ok ? result.data[0]?.companyId : undefined) ??
		mockPostings[0].companyId;

	return (
		<PageShell>
			<RoleHeader
				title="Tus ofertas"
				description="Cada oferta pasa por el agente de Mercado, que extrae requisitos, y por el Auditor, que detiene las que discriminan antes de publicarlas."
				actions={
					<a
						href="#nueva-oferta"
						className={cn(buttonVariants({ size: "lg" }), "h-11 px-4 text-sm")}
					>
						<Plus aria-hidden="true" />
						Nueva oferta
					</a>
				}
			/>

			<PostingIngest companyId={companyId} />

			<nav aria-label="Filtrar por estado" className="flex flex-wrap gap-1">
				{([undefined, ...FILTERS] as const).map((value) => {
					const href = (
						value ? `/empresa?estado=${value}` : "/empresa"
					) as Route;
					const active = value === status;
					return (
						<Link
							key={value ?? "todas"}
							href={href}
							aria-current={active ? "page" : undefined}
							className={cn(
								"flex h-9 items-center border px-3 text-sm transition-colors hover:bg-muted",
								active &&
									"border-primary bg-primary text-primary-foreground hover:bg-primary",
							)}
						>
							{value ? postingStatusMeta[value].label : "Todas"}
						</Link>
					);
				})}
			</nav>

			{result.ok ? (
				<section aria-labelledby="listado" className="flex flex-col gap-4">
					<div className="flex flex-wrap items-center justify-between gap-3">
						<h2
							id="listado"
							className="font-medium text-muted-foreground text-sm"
						>
							{plural(result.data.length, "oferta", "ofertas")}
							{status
								? ` en estado «${postingStatusMeta[status].label.toLowerCase()}»`
								: ""}
						</h2>
						<DataSourceNote source={result.source} reason={result.reason} />
					</div>
					{result.data.length > 0 ? (
						<PostingList postings={result.data} />
					) : (
						<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-14 text-center">
							<Inbox
								className="size-8 text-muted-foreground"
								aria-hidden="true"
							/>
							<p className="font-medium">
								{status
									? `No tienes ofertas en estado «${postingStatusMeta[status].label.toLowerCase()}».`
									: "Todavía no has publicado ofertas."}
							</p>
							<p className="max-w-sm text-muted-foreground text-sm">
								{status
									? "Prueba con otro estado o revisa todas tus ofertas."
									: "Pega el texto de una oferta o sube una foto y el agente de Mercado la estructura por ti."}
							</p>
							{status ? (
								<Link
									href="/empresa"
									className="text-primary text-sm underline underline-offset-4"
								>
									Ver todas las ofertas
								</Link>
							) : null}
						</div>
					)}
				</section>
			) : (
				<ErrorState
					title="No pudimos cargar tus ofertas"
					message={result.message}
				/>
			)}
		</PageShell>
	);
}
