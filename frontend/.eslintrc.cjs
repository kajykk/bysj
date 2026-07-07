module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true
  },
  extends: [
    'eslint:recommended',
    '@vue/typescript/recommended',
    'plugin:vue/vue3-recommended'
  ],
  parserOptions: {
    ecmaVersion: 2021,
    parser: '@typescript-eslint/parser',
    sourceType: 'module'
  },
  plugins: ['@typescript-eslint', 'vue'],
  rules: {
    // 错误级别 - 可运行优先
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',

    // Vue 规则
    'vue/multi-word-component-names': 'off',
    'vue/no-multiple-template-root': 'off',

    // TypeScript 规则 - 首轮适度放宽
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', ignoreRestSiblings: true }],

    // 风格规则 - 由 Prettier 处理，ESLint 不重复
    'quotes': 'off',
    'semi': 'off',
    'indent': 'off'
  },
  ignorePatterns: [
    'dist',
    'node_modules',
    'coverage',
    '*.d.ts'
  ],
  overrides: [
    {
      // 测试文件允许使用 any (mock 对象、类型绕过是测试中的常见模式)
      files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx'],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off'
      }
    }
  ]
}
