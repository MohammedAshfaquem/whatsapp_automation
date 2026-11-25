import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import postcss from 'postcss';
import { expect, test } from 'vitest';
const require = createRequire(import.meta.url);

test('the shipped CSS pipeline generates customer panel layout and responsive utilities', async () => {
  const config = require('../postcss.config.cjs');
  const result = await postcss(config.plugins).process(readFileSync(resolve('src/index.css'), 'utf8'), {from: resolve('src/index.css')});
  const declarations = (selector: string) => {
    const values: Record<string,string> = {};
    result.root.walkRules(selector, rule => {rule.walkDecls(declaration => { values[declaration.prop] = declaration.value; });});
    return values;
  };
  expect(declarations('.fixed').position).toBe('fixed');
  expect(declarations('.inset-0').inset).toBe('0px');
  expect(declarations('.flex').display).toBe('flex');
  expect(declarations('.w-80').width).toBe('20rem');
  expect(declarations('.border-l')['border-left-width']).toBe('1px');
  let widePanel = false;
  result.root.walkAtRules('media', rule => {
    if(rule.params === '(min-width: 1280px)') rule.walkRules('.xl\\:w-96', widthRule => {
      widthRule.walkDecls('width', declaration => {widePanel = declaration.value === '24rem';});
    });
  });
  expect(widePanel).toBe(true);
  expect(result.css).not.toContain('@tailwind');
});
