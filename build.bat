pyinstaller -F main.pyw ^
    --icon=Angel.ico ^
    --add-data "Angel.ico;." ^
    --add-data "About.txt;." ^
    --add-data "AllArtefactsNoAdventure.xml;." ^
    --add-data "AllSpellsNoAdventure.xml;." ^
    --add-data "RAB*.xml;." ^
    --add-data "spells_*.xml;." ^
    --add-data "7z.exe;." ^
    --add-data "MapScript.*;." ^