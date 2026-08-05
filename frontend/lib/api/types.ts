import { z } from "zod";

const metricScoreSchema = z.object({
  name: z.string(),
  value: z.number(),
  subscore: z.number(),
  weight: z.number(),
  weight_norm: z.number(),
});

const dimensionSchema = z.object({
  name: z.string(),
  score: z.number(),
  weight: z.number(),
  weight_norm: z.number(),
  contribution: z.number(),
  metrics: z.array(metricScoreSchema),
});

const scoringResultSchema = z.object({
  total: z.number(),
  grade: z.string(),
  label: z.string(),
  dimensions: z.array(dimensionSchema),
});

export const scoringResponseSchema = z.discriminatedUnion("status", [
  z.object({
    status: z.literal("ok"),
    coverage: z.number(),
    missing_core_dimensions: z.array(z.string()),
    missing_metrics: z.array(z.string()),
    result: scoringResultSchema,
  }),
  z.object({
    status: z.literal("insufficient_data"),
    coverage: z.number(),
    missing_core_dimensions: z.array(z.string()),
    missing_metrics: z.array(z.string()),
    result: z.null(),
  }),
]);

export type ScoringResponse = z.infer<typeof scoringResponseSchema>;

export type ScoringInput = {
  symbol: string;
  as_of_date: string;
  metrics: Record<string, number>;
};
