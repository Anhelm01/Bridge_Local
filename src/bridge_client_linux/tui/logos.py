"""
bridge_client_linux.tui.logos — Официальные ASCII логотипы Bridge Local.

Зафиксированы в Подфазе 04.5:
  1. BRIDGES_MASTER: Полноэкранный Neofetch сплэш-экран (подвесной мост + 8-лучевая сеть).
  2. DRAWBRIDGE_INDUSTRIAL: Оперативный разводной мост для рабочих окон.
  3. DRAWBRIDGE_HEADER: Компактная 4-строчная шапка оперативного HUD.
"""

from __future__ import annotations

# 1. BRIDGES MASTER — для полноэкранного экрана приветствия (Neofetch)
BRIDGES_MASTER = r"""
                           .::.
                       .:/XXXXXX\:.
                    .:+HMM@@@@@@MMH+:.
                  . =XMM@##[#  #]##@MMX= .
                . +HMM@#-         -#@MMH+ .
              . =XMM@#-   /\   /\   -#@MMX= .
            . :dMM@#-    /  \ /  \    -#@MMb: .
          . :uMM@#-     / /\ V /\ \     -#@MMu: .
       ..::[dMM@#-     | |  | |  | |     -#@MMb]::..
     .:[u8NNMM@#-      | |  | |  | |      -#@MMNN8u]:.
   .:[dMM@@@MM@#-      | | /| |\ | |      -#@MM@@@MMb]:.
 .u8NNMM@#::#@MMX==.   |_|/_|_|_\|_|   .==XMM@#::#@MMNN8u.
:dMM@#-.     .-#@MMH+-.             .-+HMM@#-.     .-#@MMb:
\XX/-          .-\@MMX=============XMM@/-.          -\XX/
╔═════════════════════════════════════════════════════════╗
║  [#]     B  R  I  D  G  E  S     L  O  C  A  L     [#]  ║
║          ///  S T R A N D   N E T W O R K  ///          ║
╚═════════════════════════════════════════════════════════╝
/XX\-          .-/MM@X=============XMM@\-.          -/XX\
:dMM@#-.     .-#@MMH+-  \  \ | /  /  -+HMM@#-.     .-#@MMb:
 'u8NNMM@#::#@MMX==.  \  \  \|/  /  /  .==XMM@#::#@MMNN8u'
   ':[dMM@@@MM@#-   \  \  \  |  /  /  /   -#@MM@@@MMb]:'
     .:[u8NNMM@#- ---+---+---+---+---+--- -#@MMNN8u]:.
       ''::[dMM@#-    \   \  |  /   /    -#@MMb]::''
          ' :uMM@#-    \   \ | /   /    -#@MMu: '
            ' :dMM@#- --\---+---+--/-- -#@MMb: '
              ' =XMM@#-  \  \|/  /  -#@MMX= '
                ' +HMM@#- \  |  / -#@MMH+ '
                  ' =XMM@#--\+-/--#@MMX= '
                    ' :+HMM\#|#/MMH+: '
                       ':/XXXXXX\:'
                           '::'
"""

# 2. DRAWBRIDGE INDUSTRIAL — для оперативных рабочих окон и HUD
DRAWBRIDGE_INDUSTRIAL = r"""
                     .---:::///////:::---.
                 .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
              .-+XMM@@MM##XX++++++XX##MM@@MMX+-.
            ./HMM@#X+-.     ▄      ▄     .-+X#@MMH/.
          ./XMM#X-.        /║      ║\        .-X#MMX/.
        .+MM@X-.          //║  ||  ║\\          .-X@MM+.
       .+MM#-.           // ║  ||  ║ \\           .-#MM+.
      ./MM#-            //[X]║ || ║[X]\\            -#MM/.
     .X@M:             // [X]║ || ║[X] \\            :M@X.
     :MM+             //  [X]║ || ║[X]  \\            +MM:
     =MM-            //───[X]║ || ║[X]───\\           -MM=
     :MM+           //    [X]║ || ║[X]    \\          +MM:
     .X@M:         //     [X]║ || ║[X]     \\        :M@X.
      ./MM#-      //──────[X]║ || ║[X]──────\\      -#MM/.
       .+MM#-.   (o)═════════╝ || ╚═════════(o)   .-#MM+.
        .+MM@X-.       ▲   ▲   ▲   ▲   ▲        .-X@MM+.
          ./XMM#X-.   ═╩═══╩═══╩═══╩═══╩═══   .-X#MMX/.
            ./HMM@#X+-.                     .-+X#@MMH/.
              .-+XMM@@MM##XX++++++XX##MM@@MMX+-.
                 .-/+%XXHHMMMMMMMMMMMMHHXX%+/-.
                     .---:::///////:::---.
╔══════════════════════════════════════════════════════════╗
║             D   R   A   W   B   R   I   D   G   E        ║
║        ///   B O T H   S T I C K   A N D   R O P E   /// ║
║          TO PROTECT WITH STICK · TO CONNECT WITH ROPE    ║
╚══════════════════════════════════════════════════════════╝
"""

# 3. Компактная версия DRAWBRIDGE INDUSTRIAL для верхней плашки окон
DRAWBRIDGE_HEADER = r"""      .▄█ ││ █▄.       D R A W B R I D G E  ::  B R I D G E   L O C A L
     //║  ||  ║\\      /// BOTH STICK AND ROPE : TO PROTECT AND CONNECT
    //[X]║||║[X]\\     [LNX: 192.168.1.104 ◄════► WIN: 192.168.1.150]
   (o)═══╝||╚═══(o)    STATUS: 0.38ms [OK] · POCKET: 100% · NOTES: 0 UNREAD"""
