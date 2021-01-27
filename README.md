# opsi Command Line Interface

Hier its ein Entwurf eines Konzepts für ein mögliches allgemeines Command Line Interfaces (cli) für opsi

## Genereller Ansatz

Ziel ist ein cli, was in der Lage ist, die verschiedenen Funktionen von opsi zu steuern und einheitlich Zugriff auf Konfiguration und Features zu liefern.
Das Handling soll im Einklang mit gängigen Standards, intuitiv und flexibel sein.
Die enthaltenen Funktionen sollen in Kommandos und sub-Kommandos gegliedert sein.
Sie sollen in kompilierter Form verteilt werden, sodass sie umgebungsunabhängig und robust gegen Störungen sind.
Zusätzlich soll es möglich sein, benutzerdefinierte Erweiterungen (plugins) hinzuzufügen, die als Kommandos in die cli eingebettet werden.
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
@cli.command(short_help='kurzer Hilfetext fuer sub-Kommando')
def someotherfunction():
```
angelegt. Das kwarg ```name``` ist optional und muss nur angegeben werden, wenn der Name im handling anders sein soll, als der Funktionsname.

Argumente und Optionen können analog über decorator einzelnen (sub-)Kommandos angehängt werden:
```python
@cli.command(short_help='optional short help')
@click.argument('path', type=click.Path(exists=True))
@click.option('--log-level', "-l", default="warning", type=click.Choice(['critical', 'error', "warning", "info", "debug"]))
def myfunc(path, log_level):
```
Dabei ist das kwarg ```type``` optional, hilft aber bei Typensicherheit und autocompletion.
Analog zu argparse und co. können hier default-Werte festgelegt werden, ob der parameter optional ist, wie oft er angegeben werden kann, ob environment-Variables eingebunden werden sollen, etc.
Eine ```--help``` option wird per default bereitgestellt und die Ausgabe enthält Angaben zur usage, den docstring!! und subkommandos (mit deren short_help).

### Verwaltung von Plugins

Um das cli dynamisch und benutzerdefiniert erweitern zu können, wird ein Mechanismus zum einbetten externer Kommandos bereitgestellt.
Diese können, wenn sie in Form eines python-Packages gegeben sind, per ```opsi plugin add <path>``` hinzugefügt werden.
In diesen python-Packages können auch externe libraries genutzt werden, solange sie auf https://pypi.org/ verfügbar sind (ggfs erweiterbar...).
Das hinzufügen funktioniert so, dass der code gescannt wird um eine Liste von dependencies zu erzeugen, welche dann vom pypi in ein lokales lib-Verzeichnes installiert werden.
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
