#!/usr/bin/env python3
"""The application shell (web/layout.js): how it measures, opens and listens.

There is no browser here, so two kinds of test. The first reads web/layout.js
and asserts the code shape that implements each fix, as test_gate.py does for
the page's RULE_SET. The second runs layout.js under node against a small fake
DOM and checks the behaviour itself; it is skipped where node is absent, as it
is in preflight's python-only shell.

    python3 -m unittest tools/test_layout.py
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "web" / "layout.js").read_text()


def function_body(name):
    """The text of `function name(...) { ... }`, braces balanced."""
    m = re.search(r"function " + re.escape(name) + r"\s*\([^)]*\)\s*\{", JS)
    if not m:
        raise AssertionError("no function " + name)
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(JS[i], 0)
        i += 1
    return JS[m.end():i - 1]


class Shape(unittest.TestCase):
    def test_widths_resolved_to_px_not_parsefloat(self):
        body = function_body("measure")
        self.assertNotIn("parseFloat", body)
        self.assertIn("getBoundingClientRect", body)
        self.assertIn("var(", body)

    def test_widths_measured_again_on_resize(self):
        self.assertRegex(function_body("onResize"), r"measure\(\);\s*apply\(\);")
        self.assertIn("new ResizeObserver(function () { onResize(); })", JS)
        self.assertIn("addEventListener('resize', onResize)", JS)
        self.assertIn("removeEventListener('resize', onResize)", JS)

    def test_background_open_held_until_there_is_a_width(self):
        settle = function_body("settle")
        self.assertIn("root.clientWidth <= 0", settle)
        self.assertIn("cardLeavesContent()", settle)
        self.assertIn("settle()", function_body("apply"))
        add = JS[JS.index("addCard: function"):JS.index("removeCard: function")]
        self.assertIn("c.pending = true", add)
        self.assertNotIn("root.clientWidth", add)

    def test_transient_open_honoured(self):
        add = JS[JS.index("addCard: function"):JS.index("removeCard: function")]
        self.assertIn("c.open = !!spec.open", add)

    def test_escape_ignores_composition_and_consumed_keys(self):
        body = function_body("onKey")
        guard = body.index("e.isComposing || e.defaultPrevented")
        self.assertLess(guard, body.index("setMenu(false)"))

    def test_mode_emitted_only_on_change(self):
        body = function_body("apply")
        self.assertIn("if (key === lastMode) return;", body)
        self.assertLess(body.index("lastMode = key"), body.index("emit('mode'"))


# A DOM just large enough for layout.js. A probe's width resolves the custom
# property it names from VARS (px, rem at 16px, or the unitless 0), and reads 0
# while the root is laid out at no width, as a hidden host would.
HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const VARS = {'--shell-nav-w':'232px','--shell-context-w':'336px',
              '--shell-content-min':'480px','--shell-context-strip-min':'120px'};
let W = 1200, ROOT = null;
function px(v){ const m=/^([\d.]+)(px|rem)?$/.exec(v||''); return m ? parseFloat(m[1])*(m[2]==='rem'?16:1) : 0; }
class N {
  constructor(tag){ this.tagName=tag; this.children=[]; this.parent=null; this.attrs={};
    this.dataset={}; this.style={cssText:''}; this.ls={}; this.text='';
    this.classList={add:()=>{}}; this.hidden=false; }
  get firstChild(){ return this.children[0]||null; }
  get lastChild(){ return this.children[this.children.length-1]||null; }
  get isConnected(){ let n=this; while(n.parent) n=n.parent; return n===ROOT||n===document.body; }
  set textContent(v){ this.children.forEach(c=>c.parent=null); this.children=[]; this.text=v; }
  get textContent(){ return this.text; }
  set innerHTML(v){ this.textContent=''; this.appendChild(new N('svg')); }
  set className(v){ this.cls=v; }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return this.attrs[k]; }
  appendChild(c){ return this.insertBefore(c,null); }
  insertBefore(c,at){ if(c.parent) c.parent.removeChild(c); const i=at?this.children.indexOf(at):-1;
    if(i<0) this.children.push(c); else this.children.splice(i,0,c); c.parent=this; return c; }
  removeChild(c){ this.children.splice(this.children.indexOf(c),1); c.parent=null; return c; }
  contains(n){ for(;n;n=n.parent) if(n===this) return true; return false; }
  addEventListener(t,f){ (this.ls[t]=this.ls[t]||[]).push(f); }
  removeEventListener(){}
  querySelector(){ return null; }
  matches(){ return false; }
  closest(){ return null; }
  focus(){ document.activeElement=this; }
  get clientWidth(){ return this===ROOT ? W : 0; }
  getBoundingClientRect(){ const m=/width:var\(([-\w]+)/.exec(this.style.cssText);
    return {width: m && W>0 ? px(VARS[m[1]]) : 0}; }
}
global.document = { body:new N('body'), activeElement:null, ls:{},
  createElement:t=>new N(t), createTextNode:t=>{const n=new N('#text'); n.text=t; return n;},
  addEventListener(t,f){ (this.ls[t]=this.ls[t]||[]).push(f); }, removeEventListener(){} };
document.activeElement = document.body;
const STORE = {};
global.localStorage = { getItem:k=>STORE[k]===undefined?null:STORE[k], setItem:(k,v)=>{STORE[k]=v;} };
let ros = [];
global.ResizeObserver = class { constructor(f){ this.f=f; ros.push(this);} observe(){} disconnect(){} };
global.window = global;
vm.runInThisContext(fs.readFileSync(process.argv[2],'utf8'));
function fire(){ ros.forEach(r=>r.f([])); }
function mount(opts){ ros=[]; ROOT=new N('div'); document.body.appendChild(ROOT); opts.root=ROOT; return Shell.mount(opts); }
function key(o){ const e=Object.assign({key:'Escape',isComposing:false,defaultPrevented:false},o);
  document.ls.keydown.forEach(f=>f(e)); }
const out = {};

// 1. Widths in rem resolve to px, and an override is read again on resize.
VARS['--shell-nav-w']='20rem'; W=700;
let s = mount({storageKey:null});
out.remNav = ROOT.dataset.nav;                     // 320+480 > 700: overlay
VARS['--shell-nav-w']='10rem'; fire();
out.remNavAfter = ROOT.dataset.nav;                // 160+480 <= 700: inline
VARS['--shell-nav-w']='232px';

// 2. Mounted hidden, a remembered-open card opens once there is a width.
STORE['shell:k'] = JSON.stringify({nav:true, cards:['bg']});
W=0; s = mount({storageKey:'k', cards:[{id:'bg', title:'B', background:true}]});
out.hiddenOpen = s.isOpen('bg');
W=1200; fire();
out.shownOpen = s.isOpen('bg');

// 3. A transient card given open:true comes up open.
s = mount({storageKey:null, cards:[{id:'t', title:'T', open:true}]});
out.transientOpen = s.isOpen('t');

// 4. Escape: not while composing, not once consumed.
const tgt = s.body('t');
key({target:tgt, isComposing:true}); out.afterComposing = s.isOpen('t');
key({target:tgt, defaultPrevented:true}); out.afterConsumed = s.isOpen('t');
key({target:tgt}); out.afterEscape = s.isOpen('t');

// 5. 'mode' only on a change.
W=1200; s = mount({storageKey:null}); let n=0; s.on('mode',()=>n++);
fire(); fire(); out.modeSame = n;
W=500; fire(); out.modeChanged = n;
W=501; fire(); out.modeSameNarrow = n;
console.log(JSON.stringify(out));
"""


class Behaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("node is not on PATH")
        with tempfile.TemporaryDirectory() as d:
            h = Path(d) / "harness.js"
            h.write_text(HARNESS)
            r = subprocess.run([node, str(h), str(ROOT / "web" / "layout.js")],
                               capture_output=True, text=True, timeout=60)
        if r.returncode:
            raise AssertionError(r.stderr)
        cls.out = json.loads(r.stdout)

    def test_rem_widths_and_resize_remeasure(self):
        self.assertEqual(self.out["remNav"], "overlay")
        self.assertEqual(self.out["remNavAfter"], "inline")

    def test_hidden_mount_opens_remembered_card_later(self):
        self.assertFalse(self.out["hiddenOpen"])
        self.assertTrue(self.out["shownOpen"])

    def test_transient_open(self):
        self.assertTrue(self.out["transientOpen"])

    def test_escape_guards(self):
        self.assertTrue(self.out["afterComposing"])
        self.assertTrue(self.out["afterConsumed"])
        self.assertFalse(self.out["afterEscape"])

    def test_mode_only_on_change(self):
        self.assertEqual(self.out["modeSame"], 0)
        self.assertEqual(self.out["modeChanged"], 1)
        self.assertEqual(self.out["modeSameNarrow"], 1)


if __name__ == "__main__":
    unittest.main()
