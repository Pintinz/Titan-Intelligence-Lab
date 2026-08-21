import { describe, expect, it } from 'vitest'
import { humanizeModelAlgorithm, resolveVerdict, resolveOutcomeLabel } from './evidence-explorer'

describe('humanizeModelAlgorithm', () => {
  it('maps every real backend algorithm value to its display name', () => {
    expect(humanizeModelAlgorithm('poisson_goals_model')).toBe('Poisson Goal Distribution')
    expect(humanizeModelAlgorithm('xgboost_gbm')).toBe('XGBoost Classifier')
    expect(humanizeModelAlgorithm('logistic_regression')).toBe('Logistic Regression')
  })

  it('never renders the raw backend value for a known algorithm', () => {
    const label = humanizeModelAlgorithm('poisson_goals_model')
    expect(label).not.toContain('_')
  })

  it('falls back to a plain title-cased read for an unrecognized algorithm, not a guess', () => {
    expect(humanizeModelAlgorithm('some_future_algorithm')).toBe('Some Future Algorithm')
  })

  it('returns null for a missing algorithm rather than a placeholder string', () => {
    expect(humanizeModelAlgorithm(null)).toBeNull()
    expect(humanizeModelAlgorithm(undefined)).toBeNull()
  })
})

describe('resolveVerdict (probability vs confidence separation)', () => {
  it('resolves HOME_WIN/AWAY_WIN to the real team name, never the raw enum', () => {
    const home = { name: 'Arsenal' }
    const away = { name: 'Coventry City FC' }
    expect(resolveVerdict('HOME_WIN', home, away).text).toBe('Arsenal')
    expect(resolveVerdict('AWAY_WIN', home, away).text).toBe('Coventry City FC')
    expect(resolveVerdict('DRAW', home, away).text).toBe('Draw')
  })

  it('humanizes the generic YES/NO/OVER/UNDER outcome codes', () => {
    expect(resolveOutcomeLabel('YES')).toBe('Yes')
    expect(resolveOutcomeLabel('OVER')).toBe('Over')
  })
})
