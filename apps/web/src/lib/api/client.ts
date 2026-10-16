import createClient from "openapi-fetch";

import { ENV } from "@/env";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Location = Schemas["Location"];
export type Skill = Schemas["Skill"];
export type JobPosting = Schemas["JobPosting"];
export type PostingStatus = Schemas["PostingStatus"];
export type TimeSlot = Schemas["TimeSlot"];

/** Base del contrato: `servers[0].url` en packages/api-spec/openapi.yaml. */
export const API_BASE_URL = `${ENV.NEXT_PUBLIC_API_URL.replace(/\/+$/, "")}/api/v1`;

/** auto: mocks solo si la API falla · siempre: nunca llama a la API · nunca: muestra el error. */
export const MOCK_MODE = ENV.NEXT_PUBLIC_API_MOCKS;

export const api = createClient<paths>({ baseUrl: API_BASE_URL });
