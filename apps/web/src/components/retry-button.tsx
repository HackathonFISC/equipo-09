"use client";

import { Button } from "@puente/ui/components/button";
import { RotateCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function RetryButton() {
	const router = useRouter();
	const [pending, startTransition] = useTransition();
	return (
		<Button
			variant="outline"
			size="lg"
			disabled={pending}
			onClick={() => startTransition(() => router.refresh())}
		>
			<RotateCw
				className={pending ? "animate-spin" : undefined}
				aria-hidden="true"
			/>
			{pending ? "Reintentando…" : "Reintentar"}
		</Button>
	);
}
