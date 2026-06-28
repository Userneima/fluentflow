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
        <main className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] px-8 py-7 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <div className="mx-auto max-w-[880px]">
                <header className="mb-6 flex flex-col gap-4 border-b border-[#dedada] pb-5 dark:border-white/[0.12] md:flex-row md:items-end md:justify-between">
                    <div className="min-w-0">
                        <h1 className="font-headline text-2xl font-extrabold tracking-tight text-[#111111] dark:text-white">
                            {zh ? '关于与协议' : 'About and terms'}
                        </h1>
                        <p className="mt-2 max-w-[62ch] text-sm font-semibold leading-relaxed text-[#676970] dark:text-white/58">
                            {zh
                                ? '这里说明 FluentFlow 的使用边界、数据处理方式、账号额度和结果责任。正式公开前可继续替换为完整法律文本。'
                                : 'Product boundaries, data handling, account balance, and result responsibility live here. Full legal terms can replace this before public release.'}
                        </p>
                    </div>
                    <Link to="/" className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[14px] border border-[#dedada] bg-white px-4 text-sm font-extrabold text-[#111111] transition hover:bg-[#efeeee] active:translate-y-px dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]">
                        <SvgIcon name="arrow_back" className="text-[18px]"/>
                        {zh ? '返回开始处理' : 'Back to start'}
                    </Link>
                </header>

                <div className="overflow-hidden rounded-[22px] border border-[#dedada] bg-white dark:border-white/[0.12] dark:bg-white/[0.06]">
                    {sections.map((section, index) => (
                        <section key={section.title} className={`grid gap-3 px-5 py-5 md:grid-cols-[180px_minmax(0,1fr)] md:gap-8 ${index > 0 ? 'border-t border-[#ece8e8] dark:border-white/[0.10]' : ''}`}>
                            <h2 className="text-sm font-extrabold text-[#111111] dark:text-white">{section.title}</h2>
                            <p className="max-w-[68ch] text-sm font-semibold leading-relaxed text-[#676970] dark:text-white/58">
                                {section.body}
                            </p>
                        </section>
                    ))}
                </div>

                <p className="mt-4 text-xs font-semibold leading-relaxed text-[#85868c] dark:text-white/45">
                    {zh
                        ? '如果材料涉及商业机密、隐私、版权或专业决策，请先确认你有处理权限，并在使用结果前复查原文。'
                        : 'For confidential, private, copyrighted, or high-stakes material, confirm you have permission and review the source before relying on results.'}
                </p>
            </div>
        </main>
    );
};

export default About;
