import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { DataSourceNote, ErrorState } from "@/components/data-states";
import { PageShell, RoleHeader } from "@/components/page-shell";
import {
	PostingStatusBadge,
	postingStatusMeta,
} from "@/components/posting-list";
import {
	type Loaded,
	loadLocations,
	loadPostings,
	loadSkills,
} from "@/lib/api/catalog";
import { API_BASE_URL, type PostingStatus } from "@/lib/api/client";

export const metadata: Metadata = { title: "Datos semilla" };

function Section<T>({
	id,
	title,
	endpoint,
	result,
	children,
}: {
	id: string;
	title: string;
	endpoint: string;
	result: Loaded<T>;
	children: (data: T) => React.ReactNode;
}) {
	return (
		<section aria-labelledby={id} className="flex flex-col gap-4">
			<div className="flex flex-wrap items-end justify-between gap-3 border-b pb-3">
				<div className="flex flex-col gap-0.5">
					<h2 id={id} className="font-medium text-lg">
						{title}
					</h2>
					<code className="font-mono text-muted-foreground text-xs">
						GET {endpoint}
					</code>
				</div>
				{result.ok ? (
					<DataSourceNote source={result.source} reason={result.reason} />
				) : null}
			</div>
			{result.ok ? (
				children(result.data)
			) : (
				<ErrorState
					title={`No pudimos cargar ${title.toLowerCase()}`}
					message={result.message}
				/>
			)}
		</section>
	);
}

export default async function DatosPage() {
	await connection();
	const [postings, locations, skills] = await Promise.all([
		loadPostings(),
		loadLocations(),
		loadSkills(),
	]);

	return (
		<PageShell>
			<RoleHeader
				title="Datos semilla"
				description={
					<>
						Lo que sirve hoy la API en{" "}
						<code className="font-mono text-sm">{API_BASE_URL}</code>. Si no
						responde, la web muestra datos de ejemplo tipados con el contrato
						OpenAPI y lo indica.
					</>
				}
			/>

			<Section
				id="ofertas"
				title="Ofertas"
				endpoint="/postings"
				result={postings}
			>
				{(data) => {
					const counts = new Map<PostingStatus, number>();
					for (const p of data)
						counts.set(p.status, (counts.get(p.status) ?? 0) + 1);
					return (
						<div className="flex flex-col gap-3">
							<ul className="flex flex-wrap gap-x-6 gap-y-2">
								{(Object.keys(postingStatusMeta) as PostingStatus[]).map(
									(s) => (
										<li key={s} className="flex items-center gap-2">
											<PostingStatusBadge status={s} />
											<span className="tabular font-mono text-sm">
												{counts.get(s) ?? 0}
											</span>
										</li>
									),
								)}
							</ul>
							<p className="text-sm">
								<span className="tabular font-mono">{data.length}</span> en
								total ·{" "}
								<Link
									href="/empresa"
									className="text-primary underline underline-offset-4"
								>
									Ver en la vista de empresa
								</Link>
							</p>
						</div>
					);
				}}
			</Section>

			<Section
				id="corregimientos"
				title="Corregimientos"
				endpoint="/locations"
				result={locations}
			>
				{(data) => (
					<div className="overflow-x-auto border">
						<table className="w-full min-w-[32rem] text-sm">
							<thead className="bg-muted/60 text-left text-muted-foreground">
								<tr>
									<th scope="col" className="px-3 py-2 font-medium">
										Corregimiento
									</th>
									<th scope="col" className="px-3 py-2 font-medium">
										Distrito
									</th>
									<th scope="col" className="px-3 py-2 font-medium">
										Provincia
									</th>
									<th scope="col" className="px-3 py-2 text-right font-medium">
										Lat, lng
									</th>
								</tr>
							</thead>
							<tbody>
								{data.map((l) => (
									<tr key={l.id} className="border-t">
										<td className="px-3 py-2 font-medium">{l.corregimiento}</td>
										<td className="px-3 py-2">{l.distrito}</td>
										<td className="px-3 py-2">{l.provincia}</td>
										<td className="tabular px-3 py-2 text-right font-mono text-muted-foreground text-xs">
											{l.lat != null && l.lng != null
												? `${l.lat.toFixed(4)}, ${l.lng.toFixed(4)}`
												: "—"}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</Section>

			<Section
				id="habilidades"
				title="Habilidades"
				endpoint="/skills"
				result={skills}
			>
				{(data) => (
					<ul className="flex flex-wrap gap-1.5">
						{data.map((s) => (
							<li key={s.id} className="border px-2 py-0.5 text-xs">
								{s.labelEs}
								{s.group ? (
									<span className="text-muted-foreground"> · {s.group}</span>
								) : null}
							</li>
						))}
					</ul>
				)}
			</Section>
		</PageShell>
	);
}
