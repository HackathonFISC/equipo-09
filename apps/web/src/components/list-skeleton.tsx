import { Skeleton } from "@puente/ui/components/skeleton";

import { PageShell } from "./page-shell";

/** Esqueleto de carga para las rutas por rol: reserva el espacio del encabezado y de las filas. */
export function ListSkeleton({
	rows = 4,
	narrow = false,
}: {
	rows?: number;
	narrow?: boolean;
}) {
	return (
		<PageShell width={narrow ? "narrow" : "wide"}>
			<output aria-live="polite" className="sr-only">
				Cargando…
			</output>
			<div className="flex flex-col gap-3 border-b pb-6">
				<Skeleton className="h-9 w-2/3 max-w-md" />
				<Skeleton className="h-5 w-full max-w-xl" />
			</div>
			<div className="flex flex-col border-y">
				{Array.from({ length: rows }, (_, i) => (
					<div
						key={i}
						className="flex flex-col gap-3 border-b py-5 last:border-b-0"
					>
						<Skeleton className="h-5 w-1/2" />
						<Skeleton className="h-4 w-3/4" />
					</div>
				))}
			</div>
		</PageShell>
	);
}
