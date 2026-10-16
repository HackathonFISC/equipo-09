"use client";

import { buttonVariants } from "@puente/ui/components/button";
import { cn } from "@puente/ui/lib/utils";
import type { Route } from "next";
import Link from "next/link";
import { useSyncExternalStore } from "react";

import { recallYouth } from "@/lib/youth-session";

const subscribe = () => () => {};

/** Si este navegador ya creó un perfil, ofrece retomarlo. */
export function ContinueProfile() {
	const youthId = useSyncExternalStore(subscribe, recallYouth, () => null);
	if (!youthId) return null;
	return (
		<Link
			href={`/joven/perfil?id=${youthId}` as Route}
			className={cn(
				buttonVariants({ variant: "outline", size: "lg" }),
				"h-12 w-full text-base",
			)}
		>
			Continuar con mi perfil
		</Link>
	);
}
