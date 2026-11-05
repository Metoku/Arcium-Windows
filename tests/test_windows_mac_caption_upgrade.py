"""Atomic migration of the complete earlier caption catalog; no native build."""
import difflib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from scripts import apply_windows_arc_workflow as workflow


@unittest.skipUnless(shutil.which('git'), 'Git is required')
class MacCaptionUpgradeTests(unittest.TestCase):
    def fixture(self, root, style, protected=False):
        source=root/'src'; source.mkdir()
        (source/'BUILD.gn').write_text('# partial source\n')
        group=workflow.MAC_CAPTION_SOURCE
        frame='chrome/browser/ui/views/frame/browser_frame_view_win.cc'
        header='chrome/browser/ui/views/frame/browser_frame_view_win.h'
        host='chrome/browser/ui/views/frame/browser_desktop_window_tree_host_win.cc'
        before={group:'original group\n',frame:'original frame\n',header:'original header\n',host:'original host\n'}
        old={group:'void Group() {\n    button->InvalidateLayout();\n}\n',frame:'old caption\n'}
        new=old|{frame:'shared caption\n',header:'public shared policy\n',host:'custom HWND mode\n'}
        previous=root/'patches/windows/history/mac-window-buttons-v1.patch'
        previous.parent.mkdir(parents=True)
        current=root/'mac-window-buttons.patch'
        def catalog(changes):
            return ''.join(''.join(difflib.unified_diff(
                before[p].splitlines(keepends=True),text.splitlines(keepends=True),
                fromfile='a/'+p,tofile='b/'+p)) for p,text in changes.items())
        previous.write_text(catalog(old)); current.write_text(catalog(new))
        for index,(name,text) in enumerate(before.items()):
            data=text.encode()
            if style=='CRLF' or style=='mixed' and index%2:
                data=data.replace(b'\n',b'\r\n')
            if style=='missing-final-newline':
                data=data.removesuffix(b'\n')
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        baseline={p:(source/p).read_bytes() for p in before}
        workflow.integrate(source,apply=True,patch=previous)
        if protected:
            path=source/group
            path.write_bytes(path.read_bytes().replace(b'button->InvalidateLayout();',b'button->PreferredSizeChanged();'))
        output=source/'out/Default/retained.obj';output.parent.mkdir(parents=True);output.write_bytes(b'compiled object')
        profile=source/'test-profile/Preferences';profile.parent.mkdir();profile.write_bytes(b'profile')
        return source,current,baseline,{frame,header,host}|({group} if protected else set())

    def snapshot(self,source):
        return {p.relative_to(source).as_posix():(p.read_bytes(),p.stat().st_mtime_ns)
                for p in source.rglob('*') if p.is_file()}

    def test_both_earlier_catalogs_upgrade_without_rewriting_other_source_or_outputs(self):
        for style in ('LF','CRLF','mixed','missing-final-newline'):
            for protected in (False,True):
                with self.subTest(style=style,protected=protected),tempfile.TemporaryDirectory() as folder:
                    root=Path(folder)
                    source,current,baseline,changed=self.fixture(root,style,protected)
                    before=self.snapshot(source)
                    with mock.patch.object(workflow,'ROOT',root):
                        self.assertEqual(workflow.integrate(source,patch=current),'UPDATE_AVAILABLE')
                        self.assertEqual(before,self.snapshot(source))
                        self.assertEqual(workflow.integrate(source,apply=True,patch=current),'APPLIED')
                        after=self.snapshot(source)
                        self.assertEqual({p for p in before if before[p]!=after[p]},changed)
                        self.assertEqual(workflow.integrate(source,apply=True,patch=current),'APPLIED')
                        self.assertEqual(after,self.snapshot(source))
                        self.assertEqual(workflow.integrate(source,revert=True,patch=current),'READY')
                    for p,data in baseline.items():
                        self.assertEqual((source/p).read_bytes(),data)
                    for p in ('out/Default/retained.obj','test-profile/Preferences'):
                        self.assertEqual(before[p],self.snapshot(source)[p])

    def test_unknown_partial_earlier_catalog_is_rejected_without_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,current,_,_=self.fixture(root,'CRLF',True)
            frame=source/'chrome/browser/ui/views/frame/browser_frame_view_win.cc'
            frame.write_bytes(b'unknown local caption edit\r\n')
            before=self.snapshot(source)
            with mock.patch.object(workflow,'ROOT',root),self.assertRaisesRegex(RuntimeError,'No changes made'):
                workflow.integrate(source,apply=True,patch=current)
            self.assertEqual(before,self.snapshot(source))

    def test_non_chrome_write_scope_remains_limited_to_the_exact_frame_handler(self):
        allowed='ui/views/win/hwnd_message_handler.cc'
        for path in (allowed,'ui/views/win/hwnd_message_handler_delegate.h','ui/unrelated.cc'):
            patch=f'--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-before\n+after\n'
            if path==allowed:
                self.assertEqual(workflow.patch_targets(patch),[allowed])
            else:
                with self.assertRaisesRegex(ValueError,'Unsafe patch target'):
                    workflow.patch_targets(patch)
