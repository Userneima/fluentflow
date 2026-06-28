import {Link} from 'react-router-dom';
import {useI18n} from '../app/shared.jsx';
import SvgIcon from '../components/SvgIcon.jsx';

const About = () => {
    const {lang} = useI18n();
    const zh = lang === 'zh';
    const sections = zh ? [
        {
            title: '产品边界',
            body: 'FluentFlow 用于把视频、音频、字幕和链接材料整理为转录文本、字幕文件和 AI 笔记。它是学习与知识整理工具，不替代专业法律、医疗、投资或考试报名建议。',
        },
        {
            title: '数据与隐私',
            body: '本地路线会优先在本机处理材料；云端路线会把必要文件和文本发送到配置的后端与模型服务。请不要上传没有授权处理的私密、敏感或受版权限制的材料。',
        },
        {
            title: '账号与额度',
            body: '账号用于隔离任务历史、额度和导出记录。额度会按任务预估、保留和最终结算，管理员账号可能显示为额度豁免。',
        },
        {
            title: '结果责任',
            body: '转录和 AI 笔记可能出现错字、遗漏或理解偏差。重要材料请回听原音频、检查字幕，并以你确认后的版本为准。',
        },
    ] : [
        {
            title: 'Product scope',
            body: 'FluentFlow turns videos, audio, subtitles, and links into transcripts, subtitle files, and AI notes. It is a learning and knowledge-work tool, not professional legal, medical, financial, or exam-registration advice.',
        },
        {
            title: 'Data and privacy',
            body: 'Local routes prefer processing on this machine. Cloud routes send required files and text to the configured backend and model services. Do not upload private, sensitive, copyrighted, or unauthorized material.',
        },
        {
            title: 'Account and balance',
            body: 'Accounts isolate job history, balance, and export records. Balance is estimated, reserved, and finalized per task. Admin accounts may be marked quota-exempt.',
        },
        {
            title: 'Result responsibility',
            body: 'Transcripts and AI notes can contain mistakes, omissions, or interpretation drift. For important material, review the source audio and subtitles before relying on the note.',
        },
    ];
    return (
        <main className="ml-[var(--sidebar-offset)] min-h-screen bg-surface px-10 py-10 text-on-surface transition-[margin] duration-200 ease-out">
            <div className="mx-auto max-w-4xl">
                <Link to="/" className="inline-flex items-center gap-2 text-sm font-bold text-on-surface-variant transition hover:text-on-surface">
                    <SvgIcon name="arrow_back" className="text-[18px]"/>
                    {zh ? '返回开始处理' : 'Back to Start'}
                </Link>
                <div className="mt-8 rounded-sm border ff-border-muted bg-surface-container-lowest p-8 shadow-sm">
                    <p className="text-xs font-bold uppercase tracking-wider text-primary">FluentFlow</p>
                    <h1 className="mt-2 font-headline text-3xl font-extrabold text-on-surface">
                        {zh ? '关于与协议' : 'About & terms'}
                    </h1>
                    <p className="mt-3 max-w-2xl text-sm font-semibold leading-relaxed text-on-surface-variant">
                        {zh
                            ? '这里先放产品使用须知、数据边界和账号额度说明。正式公开版本可以在这里替换为完整服务条款与隐私政策。'
                            : 'This page keeps product usage notes, data boundaries, and account balance semantics. A public release can replace it with full Terms of Service and Privacy Policy.'}
                    </p>
                    <div className="mt-8 grid gap-4">
                        {sections.map((section) => (
                            <section key={section.title} className="rounded-sm border border-outline-variant/45 bg-surface-container-low p-5">
                                <h2 className="text-base font-extrabold text-on-surface">{section.title}</h2>
                                <p className="mt-2 text-sm font-medium leading-relaxed text-on-surface-variant">
                                    {section.body}
                                </p>
                            </section>
                        ))}
                    </div>
                </div>
            </div>
        </main>
    );
};

export default About;
