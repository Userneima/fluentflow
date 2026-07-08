// ESLint flat config (v9+ / v10)
export default [
    { ignores: ['frontend/dist/**'] },
    {
        files: ['frontend/src/**/*.{jsx,js,mjs}'],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: 'module',
            globals: {
                window: 'readonly',
                document: 'readonly',
                localStorage: 'readonly',
                fetch: 'readonly',
                XMLHttpRequest: 'readonly',
                FormData: 'readonly',
                Blob: 'readonly',
                File: 'readonly',
                Headers: 'readonly',
                URL: 'readonly',
                TextDecoder: 'readonly',
                setTimeout: 'readonly',
                clearTimeout: 'readonly',
                setInterval: 'readonly',
                clearInterval: 'readonly',
                console: 'readonly',
                requestAnimationFrame: 'readonly',
                cancelAnimationFrame: 'readonly',
                AbortController: 'readonly',
                DataTransfer: 'readonly',
                Event: 'readonly',
                navigator: 'readonly',
            },
            parserOptions: {
                ecmaFeatures: { jsx: true },
            },
        },
        rules: {
            'no-unused-vars': ['warn', { vars: 'all', args: 'after-used', ignoreRestSiblings: true, varsIgnorePattern: '^_' }],
            'no-undef': 'error',
            'no-const-assign': 'error',
            'no-duplicate-imports': 'warn',
        },
    },
];
