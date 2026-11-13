"use client";

import { useId } from "react";
import type { AgreementView } from "@strategist/shared/generated/types/AgreementView";
import type { AuditWords } from "@strategist/shared/generated/types/AuditWords";
import type { FindingDetail } from "@strategist/shared/generated/types/FindingDetail";
import type { FindingReview } from "@strategist/shared/generated/types/FindingReview";
import type { ReviewState } from "@strategist/shared/generated/types/ReviewState";

import { impactText } from "./format";
import { CERTAINTY_WORDS } from "./words";

const WEB_ADDRESS = /^https?:\/\//;

function Source({ source }: { source: string }) {
  return (
    <li>
      {WEB_ADDRESS.test(source) ? (
        <a
          href={source}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-2 hover:underline"
        >
          {source}
        </a>
      ) : (
        <span>{source}</span>
      )}
    </li>
  );
}

function namedError(review: FindingReview, words: AuditWords): string | null {
  const { errorType, certainty } = review.verdict;
  if (errorType == null) return null;
  const title = words.errorTypes[errorType];
  return certainty == null
    ? title
    : `${title}, ${CERTAINTY_WORDS[certainty].toLowerCase()}`;
}

function Reviewed({
  detail,
  review,
  agreement,
  words,
}: {
  detail: FindingDetail;
  review: FindingReview;
  agreement: AgreementView | null;
  words: AuditWords;
}) {
  const text = detail.reviewText;
  const named = namedError(review, words);
  return (
    <>
      <p className="mt-1">{text?.verdictText}</p>
      {named === null ? null : (
        <>
          <h3 className="mt-2 font-medium">Error named</h3>
          <p>{named}</p>
        </>
      )}
      <p className="mt-2">{review.verdict.cause}</p>
      <p className="mt-2">{text?.literatureText}</p>
      {(review.knownFrom ?? []).length === 0 ? null : (
        <ul>
          {(review.knownFrom ?? []).map((source) => (
            <Source key={source} source={source} />
          ))}
        </ul>
      )}
      <p className="mt-2">{text?.paperText}</p>
      {text?.secondText == null ? null : (
        <>
          <p className="mt-2">{text.secondText}</p>
          {agreement === null ? null : <p>{agreement.text}</p>}
        </>
      )}
      <h3 className="mt-2 font-medium">Suggested fix</h3>
      <p>{review.cardText}</p>
      {review.impact == null ? null : (
        <p className="mt-2">
          {`Impact after review ${String(review.impact)} (screen impact ${impactText(detail.finding.impact)}): ${review.impactReason ?? ""}`}
        </p>
      )}
    </>
  );
}

export function ReviewSection({
  detail,
  agreement,
  reviewState,
  words,
}: {
  detail: FindingDetail;
  agreement: AgreementView | null;
  reviewState: ReviewState | null;
  words: AuditWords;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-6 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Review
      </h2>
      {detail.review === null ? (
        <>
          <p className="mt-1">Not reviewed yet.</p>
          {reviewState === null ? null : <p>{reviewState.text}</p>}
        </>
      ) : (
        <Reviewed
          detail={detail}
          review={detail.review}
          agreement={agreement}
          words={words}
        />
      )}
    </section>
  );
}
