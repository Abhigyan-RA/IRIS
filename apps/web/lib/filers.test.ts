import { describe, expect, it } from 'vitest';
import { professionalFilerLabel } from './filers';

describe('professionalFilerLabel', () => {
  it('drops a trailing legal form, which carries no information on screen', () => {
    expect(professionalFilerLabel('Renaissance Technologies LLC')).toBe('Renaissance Technologies');
    expect(professionalFilerLabel('Franklin Resources Inc')).toBe('Franklin Resources');
    expect(professionalFilerLabel('Invesco Ltd')).toBe('Invesco');
    expect(professionalFilerLabel('Point72 Asset Management LP')).toBe('Point72 Asset Mgt');
  });

  it('abbreviates management the way the design does', () => {
    expect(professionalFilerLabel('Millennium Management LLC')).toBe('Millennium Mgt');
    expect(professionalFilerLabel('Fidelity Management & Research Company LLC')).toBe(
      'Fidelity Mgt & Research',
    );
  });

  it('keeps a legal form that reads as part of the house name', () => {
    expect(professionalFilerLabel('State Street Corp')).toBe('State Street Corp');
    expect(professionalFilerLabel('Northern Trust Corp')).toBe('Northern Trust Corp');
  });

  it('keeps an ampersand house name intact', () => {
    expect(professionalFilerLabel('D E Shaw & Co Inc')).toBe('D E Shaw & Co');
  });

  it('leaves a name that is already professional untouched', () => {
    expect(professionalFilerLabel('Bridgewater Associates')).toBe('Bridgewater Associates');
    expect(professionalFilerLabel('Berkshire Hathaway')).toBe('Berkshire Hathaway');
  });

  it('handles punctuated legal forms and trailing separators', () => {
    expect(professionalFilerLabel('Millennium Management, L.L.C.')).toBe('Millennium Mgt');
    expect(professionalFilerLabel('Tiger Global Management, LLC')).toBe('Tiger Global Mgt');
  });

  it('never returns an empty label, since a row must still name its fund', () => {
    expect(professionalFilerLabel('LLC')).toBe('LLC');
    expect(professionalFilerLabel('Management LLC')).toBe('Mgt');
  });
});
