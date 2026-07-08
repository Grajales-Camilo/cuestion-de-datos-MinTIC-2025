import React, { useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';

export default function RichTextEditor({ content, onChange, placeholder }) {
    const editor = useEditor({
        extensions: [
            StarterKit,
        ],
        content: content,
        immediatelyRender: false,
        editorProps: {
            attributes: {
                class: 'prose prose-sm sm:prose lg:prose-lg xl:prose-xl focus:outline-none min-h-[150px] max-w-none text-slate-700 placeholder-slate-400',
            },
        },
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            // Avoid infinite loops if content is same
            if (html !== content) {
                onChange(html);
            }
        },
    });

    // Update editor content if prop changes externally (e.g. "Copy to Canvas")
    useEffect(() => {
        if (editor && content !== editor.getHTML()) {
            editor.commands.setContent(content);
        }
    }, [content, editor]);

    if (!editor) {
        return null;
    }

    return (
        <div className="rich-text-editor">
            {/* Simple Toolbar */}
            <div className="flex gap-2 mb-2 border-b border-slate-100 pb-2">
                <button
                    onClick={() => editor.chain().focus().toggleBold().run()}
                    className={`p-1 rounded hover:bg-slate-100 ${editor.isActive('bold') ? 'bg-slate-200 text-slate-900' : 'text-slate-500'}`}
                    title="Bold"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 12h8a4 4 0 100-8H6v8zm0 0v8" /></svg>
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                    className={`p-1 rounded hover:bg-slate-100 ${editor.isActive('italic') ? 'bg-slate-200 text-slate-900' : 'text-slate-500'}`}
                    title="Italic"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                    className={`p-1 rounded hover:bg-slate-100 ${editor.isActive('bulletList') ? 'bg-slate-200 text-slate-900' : 'text-slate-500'}`}
                    title="Bullet List"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" /></svg>
                </button>
            </div>

            <EditorContent editor={editor} />

            {!editor.getText() && (
                <div className="absolute top-[60px] left-0 text-slate-300 pointer-events-none italic">
                    {placeholder}
                </div>
            )}
        </div>
    );
}
