# opsi Command Line Interface

Hier ist ein Entwurf eines Konzepts für ein mögliches allgemeines Command Line Interface (cli) für opsi.

## Genereller Ansatz

Ziel ist ein cli, was in der Lage ist, die verschiedenen Funktionen von opsi zu steuern und einheitlich Zugriff auf Konfiguration und Features zu liefern.
Das Handling soll im Einklang mit gängigen Standards, intuitiv und flexibel sein.
Die enthaltenen Funktionen sollen in Kommandos und Subkommandos gegliedert sein.
Sie sollen in kompilierter Form verteilt werden, sodass sie umgebungsunabhängig und robust gegen Störungen sind.
Zusätzlich soll es möglich sein, benutzerdefinierte Erweiterungen (plugins) hinzuzufügen, die als Kommandos in das cli eingebettet werden.
Diese Erweiterungen sollen kompakt im- und exportierbar sein, um einen einfachen Austausch in der Community zu ermöglichen.

## Umsetzung

Opsi cli ist ein python-Projekt, welches mit python3.7+ arbeitet.

### Kommandos, Argumente und Optionen

Als framework für den grundsätzlichen Aufbau des cli wird click https://palletsprojects.com/p/click/ genutzt.
Ein Kommando kann über den decorator
```python
@click.group(name="name_des_kommandos", short_help="kurzer Hilfetext fuer Kommando")
def cli():
```
als Funktion angelegt werden. Subkommandos werden über den decorator
```python
@cli.command(short_help='kurzer Hilfetext fuer Subkommando')
def someotherfunction():
```
angelegt. Das kwarg ```name``` ist optional und muss nur angegeben werden, wenn der Name im handling anders sein soll, als der Funktionsname.

Argumente und Optionen können analog über decorator einzelnen (Sub-)Kommandos angehängt werden:
```python
@cli.command(short_help='optional short help')
@click.argument('path', type=click.Path(exists=True))
@click.option('--log-level', "-l", default="warning", type=click.Choice(['critical', 'error', "warning", "info", "debug"]))
def myfunc(path, log_level):
```
Dabei ist das kwarg ```type``` optional, hilft aber bei Typensicherheit und autocomplete.
Analog zu argparse und co. können hier default-Werte festgelegt werden, ob der Parameter optional ist, wie oft er angegeben werden kann, ob environment-variables eingebunden werden sollen, etc.
Eine ```--help``` Option wird per default bereitgestellt und die Ausgabe enthält Angaben zur usage, den docstring!! und Subkommandos (mit deren short_help).

### Verwaltung von Plugins

Um das cli dynamisch und benutzerdefiniert erweitern zu können, wird ein Mechanismus zum Einbetten externer Kommandos bereitgestellt.
Diese können, wenn sie in Form eines python-Packages gegeben sind, per ```opsi plugin add <path>``` hinzugefügt werden.
In diesen python-Packages können auch externe libraries genutzt werden, solange sie auf https://pypi.org/ verfügbar sind (ggfs erweiterbar...).
Das Hinzufügen funktioniert so, dass der Code gescannt wird, um eine Liste von dependencies zu erzeugen, welche dann vom pypi in ein lokales lib-Verzeichnis installiert werden.
Alternativ kann auch eine ```requirements.txt```-Datei bereitgestellt werden, welche die Abhängigkeiten spezifiziert - in dem Fall wird diese genutzt.

So hinzugefügte plugins können kompakt als .opsiplugin-Datei (zip-Archiv) exportiert werden mit dem Befehl ```opsi plugin export <name>```.
.opsiplugin Dateien enthalten den Code des plugins nebst einer ```requirements.txt```, in der die Abhängigkeiten stehen.
Auf diese Weise exportierte plugins können einfach per ```opsi plugin add <path>``` wieder importiert werden (ggfs auf einem anderen System).
So ist ein einfacher Austausch von plugins innerhalb der Community möglich.

## Sonstiges

### Shell autocomplete

Mit dem Skript ```install.sh``` werden shell-completion Files generiert, welche für bash, zsh und fish registriert werden.
Das geschieht durch entsprechende Einträge in .bashrc, .zshrc und .config/fish/completions/ sofern diese shells vorhanden sind.
Dadurch können die jeweiligen shells per TAB Kommandos, Optionen und teilweise auch Argumente vervollständigen.
Mit TAB TAB wird eine Liste möglicher Werte angezeigt.

### Einbinden externer C libraries

Manche python-Bibliotheken nutzen zur Laufzeit C libraries des Systems (Beispiel: magic nutzt libmagic). Das ist auch bei der Nutzung externer plugins möglich.
Dabei sei aber darauf hingewiesen, dass das Resultierende Program nur dann funktioniert, wenn die benötigten libraries auf dem Zielsystem vorhanden sind.
Das Verhalten kann also auch Änderungen unterworfen sein, in verschiedenen Umgebungen oder mit verschiedenen Versionen der C libraries.
Daher ist es empfohlen, wenn möglich, darauf zu verzichten.

## Entwicklung
### Ausführungsgeschwindigkeit
Gerade für die Shell-Auto-Completion ist es wichtig, dass opsi-cli wenig Ausführungszeit benötigt.
Das Start-Verhalten kann mit viztracer sehr gut analysiert werden:

```bash
poetry run pip install viztracer
_OPSI_CLI_COMPLETE=zsh_source poetry run viztracer opsi-cli foo
poetry run vizviewer result.json
```