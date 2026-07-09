// import_to_premiere.jsx — 프리미어 원클릭 가져오기 (Premiere Auto-Edit)
//
// 하는 일: 방금 편집한 결과(output 폴더)를 한 번에 프리미어로 가져온다.
//   1) _cut.xml (컷 시퀀스) 가져오기
//   2) _cut.srt (자막) 가져와서 캡션 트랙에 자동 배치
//   3) 그 시퀀스를 열기
// → 손으로 하던 'XML 가져오기 + 자막 가져오기 + 드래그 + CC 켜기'가 실행 한 번으로.
//
// 실행: 프리미어  File > Scripts > Run Script File...  에서 이 파일 선택.
//   (자주 쓰면 프리미어 Scripts 폴더에 복사 → File > Scripts 메뉴에 상주)
//
// ExtendScript(ES3)라 var/고전 for문만 사용. 자막 배치가 실패해도 XML은 들어오게 방어적으로 처리.

// @target premierepro
(function () {
    var SETTINGS_NAME = "bibl_premiere_output.txt"; // 마지막 output 폴더 기억

    function readFile(f) {
        if (!f || !f.exists) return null;
        f.encoding = "UTF-8";
        f.open("r");
        var s = f.read();
        f.close();
        return s;
    }
    function writeFile(f, text) {
        try { f.encoding = "UTF-8"; f.open("w"); f.write(text); f.close(); return true; }
        catch (e) { return false; }
    }
    function baseName(p) {
        p = String(p).replace(/\\/g, "/");
        return p.substring(p.lastIndexOf("/") + 1);
    }

    // ── output 폴더 찾기 ─────────────────────────────────────────────
    // 우선순위: (1) 스크립트 옆(프로젝트 premiere/ 에서 실행) → ../output
    //          (2) 지난번 기억한 폴더  (3) 사용자에게 한 번 물어보기
    function findOutputDir() {
        var candidates = [];
        try {
            var self = new File($.fileName);           // 이 스크립트 경로
            var proj = self.parent ? self.parent.parent : null; // premiere/ -> 프로젝트 루트
            if (proj) candidates.push(new Folder(proj.fsName + "/output"));
        } catch (e) {}
        var remembered = new File(Folder.userData.fsName + "/" + SETTINGS_NAME);
        var rememberedPath = readFile(remembered);
        if (rememberedPath) candidates.push(new Folder(rememberedPath.replace(/[\r\n]+$/, "")));

        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i] && candidates[i].exists) return candidates[i];
        }
        // 못 찾으면 한 번만 직접 선택
        alert("편집 결과(output) 폴더를 못 찾았어요.\noutput 폴더를 한 번만 골라주세요. (다음부터 기억합니다)");
        var picked = Folder.selectDialog("Premiere Auto-Edit 의 output 폴더 선택");
        if (picked) { writeFile(remembered, picked.fsName); return picked; }
        return null;
    }

    // ── 가져올 XML/SRT 결정: _latest.json 우선, 없으면 가장 최근 _cut.xml ──
    function resolveTargets(outDir) {
        var latest = new File(outDir.fsName + "/_latest.json");
        var txt = readFile(latest);
        if (txt) {
            try {
                var obj = eval("(" + txt + ")");      // 우리 엔진이 만든 파일 (ES3엔 JSON 없음)
                if (obj && obj.xml) {
                    return { xml: obj.xml, srt: obj.srt || null, seq: obj.seq_name || null };
                }
            } catch (e) {}
        }
        // 폴백: 가장 최근 *_cut.xml
        var xmls = outDir.getFiles("*_cut.xml");
        if (!xmls || xmls.length === 0) return null;
        xmls.sort(function (a, b) { return b.modified.getTime() - a.modified.getTime(); });
        var xml = xmls[0];
        var srt = new File(xml.fsName.replace(/_cut\.xml$/, "_cut.srt"));
        return { xml: xml.fsName, srt: (srt.exists ? srt.fsName : null), seq: null };
    }

    // ── 프로젝트에서 이름으로 시퀀스 찾기 ──
    function findSequence(name) {
        try {
            var seqs = app.project.sequences;
            for (var i = 0; i < seqs.numSequences; i++) {
                if (seqs[i].name === name) return seqs[i];
            }
        } catch (e) {}
        return null;
    }
    // 가져오기 직전/직후 시퀀스 목록 비교로 '새로 생긴' 시퀀스 찾기 (이름 못 믿을 때)
    function sequenceIds() {
        var ids = {};
        try {
            var seqs = app.project.sequences;
            for (var i = 0; i < seqs.numSequences; i++) ids[seqs[i].sequenceID] = seqs[i];
        } catch (e) {}
        return ids;
    }
    function newSequenceSince(before) {
        try {
            var seqs = app.project.sequences;
            for (var i = 0; i < seqs.numSequences; i++) {
                if (!before[seqs[i].sequenceID]) return seqs[i];
            }
        } catch (e) {}
        return null;
    }

    // ── rootItem에서 이름으로 projectItem 찾기 ──
    function findProjectItem(nameNeedle) {
        try {
            var root = app.project.rootItem;
            for (var i = 0; i < root.children.numItems; i++) {
                var it = root.children[i];
                if (String(it.name).indexOf(nameNeedle) !== -1) return it;
            }
        } catch (e) {}
        return null;
    }

    // ── 실행 ────────────────────────────────────────────────────────
    if (!app || !app.project) { alert("프리미어 프로젝트를 먼저 열어주세요."); return; }

    var outDir = findOutputDir();
    if (!outDir) return;
    var t = resolveTargets(outDir);
    if (!t) { alert("output 폴더에서 편집 결과(_cut.xml)를 찾지 못했어요.\n먼저 edit.bat 으로 영상을 편집하세요."); return; }

    var msg = [];
    var beforeSeqs = sequenceIds();

    // 1) XML(+SRT) 가져오기
    var paths = [t.xml];
    if (t.srt) paths.push(t.srt);
    var ok = false;
    try {
        ok = app.project.importFiles(paths, true, app.project.rootItem, false);
    } catch (e) {
        // 배열 시그니처가 안 먹는 버전 대비: 하나씩
        try {
            app.project.importFiles([t.xml], true, app.project.rootItem, false);
            if (t.srt) app.project.importFiles([t.srt], true, app.project.rootItem, false);
            ok = true;
        } catch (e2) { alert("가져오기 실패:\n" + e2.toString()); return; }
    }
    msg.push("시퀀스 XML 가져옴: " + baseName(t.xml));

    // 2) 새로 생긴(또는 이름 매칭) 시퀀스 열기
    var seq = (t.seq ? findSequence(t.seq) : null) || newSequenceSince(beforeSeqs);
    if (seq) {
        try { app.project.openSequence(seq.sequenceID); } catch (e) {}
        try { app.project.activeSequence = seq; } catch (e) {}
        msg.push("시퀀스 열림: " + seq.name);
    } else {
        msg.push("[주의] 만들어진 시퀀스를 자동으로 못 찾았어요. 프로젝트 패널에서 더블클릭하세요.");
    }

    // 3) 자막(SRT)을 캡션 트랙에 자동 배치
    if (t.srt) {
        var srtItem = findProjectItem(baseName(t.srt));
        var placed = false;
        var active = null;
        try { active = app.project.activeSequence; } catch (e) {}
        if (srtItem && active && active.createCaptionTrack) {
            // 버전별 시그니처 차이 대비 몇 가지 시도
            var attempts = [
                function () { return active.createCaptionTrack(srtItem, 0); },
                function () { var tm = new Time(); tm.seconds = 0; return active.createCaptionTrack(srtItem, tm); },
                function () { return active.createCaptionTrack(srtItem, 0, 708); }
            ];
            for (var a = 0; a < attempts.length; a++) {
                try { attempts[a](); placed = true; break; } catch (e) {}
            }
        }
        if (placed) msg.push("자막 캡션 트랙 자동 배치 완료 ✓");
        else msg.push("[자막] 프로젝트 패널에 가져옴 — 캡션 자동배치가 안 돼\n     '" + baseName(t.srt) + "' 을 타임라인 위쪽으로 드래그하세요.");
    } else {
        msg.push("[자막] _cut.srt 를 못 찾았어요.");
    }

    alert("완료\n\n" + msg.join("\n") + "\n\n(자막이 화면에 안 보이면 프로그램 모니터의 CC 버튼 → 캡션 표시 켜기)");
})();
