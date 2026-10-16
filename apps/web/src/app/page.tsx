import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { PageShell } from "@/components/page-shell";
import { roles } from "@/lib/roles";

export default function Home() {
	return (
		<PageShell className="gap-12 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start lg:gap-16 lg:py-16">
			<section
				aria-labelledby="titulo"
				className="flex flex-col gap-6 lg:sticky lg:top-28"
			>
				<h1
					id="titulo"
					className="text-balance font-semibold text-3xl leading-[1.1] tracking-tight sm:text-5xl sm:leading-[1.05]"
				>
					Del barrio al primer empleo, con una persona revisando cada decisión.
				</h1>
				<p className="max-w-prose text-pretty text-muted-foreground sm:text-lg">
					Puente conecta a jóvenes con ofertas a las que de verdad pueden
					llegar: calcula el traslado, el costo del pasaje y el horario antes de
					recomendar, y explica cada match.
				</p>
				<p className="max-w-prose text-pretty text-muted-foreground">
					El desempleo juvenil en Panamá llega al{" "}
					<strong className="tabular font-mono font-semibold text-foreground">
						19.9 %
					</strong>{" "}
					(INEC), y Panamá Oeste es la región más afectada.
				</p>
			</section>

			<section aria-labelledby="roles" className="flex flex-col gap-4">
				<h2 id="roles" className="font-medium text-lg">
					¿Con qué rol entras?
				</h2>
				<ul className="flex flex-col border-y">
					{roles.map((role) => {
						const Icon = role.icon;
						return (
							<li key={role.id} className="border-b last:border-b-0">
								<Link
									href={role.href}
									className="group grid grid-cols-[auto_1fr_auto] items-start gap-x-4 gap-y-1 px-2 py-5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 sm:px-4"
								>
									<span className="row-span-2 flex size-11 items-center justify-center bg-secondary text-secondary-foreground">
										<Icon className="size-5" aria-hidden="true" />
									</span>
									<span className="flex flex-wrap items-baseline gap-x-3">
										<span className="font-semibold text-base">
											{role.label}
										</span>
										<span className="text-muted-foreground text-xs">
											{role.context}
										</span>
									</span>
									<ArrowRight
										className="row-span-2 mt-3 size-5 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary"
										aria-hidden="true"
									/>
									<span className="col-start-2 flex flex-col gap-1">
										<span className="font-medium text-foreground">
											{role.promise}
										</span>
										<span className="text-pretty text-muted-foreground text-sm">
											{role.detail}
										</span>
									</span>
								</Link>
							</li>
						);
					})}
				</ul>
				<p className="text-muted-foreground text-sm">
					Demo del Reto 3 · Hackathon FISC 2026. El selector de rol reemplaza al
					inicio de sesión.
				</p>
			</section>
		</PageShell>
	);
}
