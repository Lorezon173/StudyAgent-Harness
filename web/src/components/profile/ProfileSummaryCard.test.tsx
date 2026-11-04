// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import ProfileSummaryCard from './ProfileSummaryCard';
import { profile } from '../../test/setup';
import { ProfileSummary } from '../../types';
const base: ProfileSummary = { profile_revision: 4, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 2, mastery_score: 80, metric_kind: 'assessed_mean', assessment_coverage: 0.5 };
it('preserves supplied score, coverage, revision and distinguishes zero from null', () => {
  const { rerender } = render(<ProfileSummaryCard profile={profile()} summary={base} activeNodeId={null} />);
  expect(screen.getByText('80%')).toBeTruthy(); expect(screen.getByText(/1 \/ 2（50%）/)).toBeTruthy(); expect(screen.getByText(/REV 4/)).toBeTruthy();
  rerender(<ProfileSummaryCard profile={profile()} summary={{ ...base, mastery_score: 0, assessment_coverage: 0 }} activeNodeId={null} />);
  expect(screen.getByText('0%')).toBeTruthy(); expect(screen.getByText(/1 \/ 2（0%）/)).toBeTruthy();
  rerender(<ProfileSummaryCard profile={profile()} summary={{ ...base, mastery_score: null, assessment_coverage: null, assessed_count: 0, total_count: 0 }} activeNodeId={null} />);
  expect(screen.getByText('待评估')).toBeTruthy(); expect(screen.getByText('暂无知识点')).toBeTruthy();
});
