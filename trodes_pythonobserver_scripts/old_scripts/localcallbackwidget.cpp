/*
Trodes is a free, open-source neuroscience data collection and experimental control toolbox

Copyright (C) 2012 Mattias Karlsson

This program is free software: you can redistribute it and/or modify
                               it under the terms of the GNU General Public License as published by
                               the Free Software Foundation, either version 3 of the License, or
                               (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/


#include "localcallbackwidget.h"

localCallbackWidget::localCallbackWidget(QWidget *parent)
        : QTextEdit(parent),
          scriptingProgram(NULL) {

    scriptLanguage = "";
    comDirectory = "";
    numCharRead = 0;
    useComDir = false;
    processOutputStream.setString(new QString());
    programRunning = false;
    setEnabled(false);


    scriptingProgram = new QProcess(this);
    connect(scriptingProgram,SIGNAL(readyReadStandardOutput()),this,SLOT(readDataFromProcess()));
    connect(scriptingProgram,SIGNAL(readyReadStandardError()),this,SLOT(readDataFromProcess()));

    connect(scriptingProgram,SIGNAL(started()),this,SLOT(sendInitiationText()));
    connect(this,SIGNAL(textEntered(QByteArray)),this,SLOT(sendText(QByteArray)));


    //QStringList processArguments;


    //scriptingProgram->start("/Applications/Julia-0.3.0-prerelease-09d9e34417.app/Contents/MacOS/Julia");
    //processArguments << "-i";
    //scriptingProgram->start("python", processArguments);

   //processArguments << "-nodesktop" << "-nosplash";
   //scriptingProgram->start("/Applications/MATLAB_R2013b.app/bin/matlab", processArguments);
    fileReadTimer = new QTimer;
    connect(fileReadTimer,SIGNAL(timeout()),this,SLOT(readMatlabOutputFile()));

}

localCallbackWidget::~localCallbackWidget() {
    if (scriptingProgram != NULL) {
        scriptingProgram->close();
        scriptingProgram->deleteLater();
    }

    if (programRunning) {
        killEngine();
    }
}

void localCallbackWidget::startEngine(QString language, QString path, QString initCommand) {
    QStringList processArguments;

    scriptLanguage = language;
    QFileInfo commandFile;
    commandFile.setFile(initCommand);
    commandFile.baseName();
    initiationCommand = commandFile.baseName();

    //scriptingProgram->start("/Applications/Julia-0.3.0-prerelease-09d9e34417.app/Contents/MacOS/Julia");

    //processArguments << "-i";
    //scriptingProgram->start("python", processArguments);

   if ((!programRunning) && (language == "Matlab")) {
    setEnabled(false);



#ifdef WIN32
       //Use files to communicate to programs that don't allow stdin and stdout communication
       useComDir = true;
       qsrand(QTime::currentTime().msec());
       //We create a new directory with a random number name
       comDirectory = QApplication::applicationDirPath() + QDir::separator() + "commDir" + QString("%1").arg(qrand());
       QDir().mkdir(comDirectory);

       //Create the command file
       QFile guiCommandOutput;
       guiCommandOutput.setFileName(comDirectory+"/qtGUIStream.txt");
       if( !guiCommandOutput.open( QIODevice::WriteOnly ) ) {
           qDebug() << QString("Command file could not be opened");
           return;
       }
       guiCommandOutput.close();
       numCharRead = 0;

       //Start matlab, telling it to dump it's output to a file
       processArguments << "-nodesktop" << "-nosplash" << "-r" << "startWinScQt('" + initiationCommand + "','" + comDirectory + "')" << "-logfile" << QDir::toNativeSeparators(comDirectory+"/matlaboutput.txt");
       scriptingProgram->start(path, processArguments);
#else
       processArguments << "-nodesktop" << "-nosplash";
       scriptingProgram->start(path, processArguments);
#endif




   } else if ((!programRunning) && (language == "Python")) {
       processArguments << "-i";
       scriptingProgram->start(path, processArguments);
   }

}

void localCallbackWidget::killEngine() {
    if (programRunning) {

        //Kill the program

        //If we were using files to communicate with the program (matlab on windows), we
        //need to destroy the files
        if (!comDirectory.isEmpty()) {
            if (scriptLanguage == "Matlab") {
                sendText(QString("quit").toLocal8Bit());
            }

            QThread::msleep(500);
            QDir dir(comDirectory);
            dir.setNameFilters(QStringList() << "*.*");
            dir.setFilter(QDir::Files);
            foreach(QString dirFile, dir.entryList())
            {
                dir.remove(dirFile);
            }

            QDir().rmdir(comDirectory);
            comDirectory = "";
            useComDir = false;
            numCharRead = 0;

            fileReadTimer->stop();
        } else {

            scriptingProgram->close();
        }

        programRunning = false;
        setEnabled(false);
        QTextDocument* d = document();
        d->setPlainText("");
    }
}

void localCallbackWidget::readDataFromProcess() {

    if (!useComDir) {
        QByteArray tmpProcessOutput;
        QByteArray processErrorOutput;
	processErrorOutput.append(scriptingProgram->readAllStandardError());
	tmpProcessOutput.append(scriptingProgram->readAllStandardOutput());

        insertPlainText(QString(processErrorOutput));
        insertPlainText(QString(tmpProcessOutput));

        QScrollBar *bar = verticalScrollBar();
        bar->setValue(bar->maximum());



        processOutputStream << tmpProcessOutput;
        //Pick out complete lines from the input stream
        //and search for stateScript messages
        bool moreLinesLeft = true;
        while (moreLinesLeft) {

            QString tmpLine = processOutputStream.readLine();
            if (tmpLine.isNull()) {
                moreLinesLeft = false;
            } else {

                if (tmpLine.contains("SCQTMESSAGE: ")) {
                    //If the line has the magic header, cut out the message and emit.
                    int messageStartLoc = tmpLine.indexOf("SCQTMESSAGE: ") + 13;
                    tmpLine.remove(0,messageStartLoc);
                    tmpLine.append("\n");
                    //qDebug() << "New message received: " << tmpLine;
                    emit stateScriptCommandReceived(tmpLine);
                }
            }
        }
    }
}

void localCallbackWidget::sendText(QByteArray text) {
    if (programRunning) {
        if (!useComDir) {
            scriptingProgram->write(text.data());
            scriptingProgram->write("\n");
        } else {
            QFile guiCommandOutput;
            guiCommandOutput.setFileName(comDirectory+"/qtGUIStream.txt");
            if( !guiCommandOutput.open( QIODevice::Append ) ) {
                qDebug() << QString("Output file not found.");
                return;
            }

            guiCommandOutput.write(text);
            guiCommandOutput.write("\n");

            guiCommandOutput.close();
        }

    }
}

//Public version of the function
void localCallbackWidget::sendText(QString text) {
    text.prepend("addScQtEvent('");
    text.append("');\n");
    sendText(text.toLocal8Bit());
}

void localCallbackWidget::sendInitiationText() {
    //called after the scripting program has started
    //we need to send a commanmd to initiate a 'listening' process

    programRunning = true;
    setEnabled(true);

    if (!useComDir) {
        if (scriptLanguage == "Matlab") {
            //scriptingProgram->write("startScQt('exampleScQtCallback')");
            QString initCommand = "startScQt('" + initiationCommand + "')";
            scriptingProgram->write(initCommand.toLocal8Bit());
        }
	if (scriptLanguage == "Python") {
		QString initCommand = "from PythonObserver import *\n";
		initCommand.append("startScQt('" + initiationCommand + "')\n");
		scriptingProgram->write(initCommand.toLocal8Bit());

	}
        scriptingProgram->write("\n");
    } else {
        //If we are using files to communicate instead of stdin and stdout, start a timer to check the file
        fileReadTimer->start(100);
    }
    emit programStarted();
}

void localCallbackWidget::keyPressEvent(QKeyEvent *e)
{
    char backspaceVal = 8;

    if (e->matches(QKeySequence::Paste)) { //if the paste key sequence was pressed
        paste();
    } else {
        switch (e->key()) {
        case Qt::Key_Backspace:


            if (currentEntryLine.length() > 0) {
                QTextEdit::keyPressEvent(e);
                currentEntryLine.chop(1);
            }
            break;

        case Qt::Key_Return:
                QTextEdit::keyPressEvent(e);
                //currentEntryLine.append(e->text());
                emit textEntered(currentEntryLine);
                currentEntryLine.clear();

        case Qt::Key_Left:
        case Qt::Key_Right:
        case Qt::Key_Up:
        case Qt::Key_Down:
            // skip processing
            break;
        default:

            QTextEdit::keyPressEvent(e);
            currentEntryLine.append(e->text());



        }
    }
}

void localCallbackWidget::readMatlabOutputFile() {
    QFile matlabfile;
    matlabfile.setFileName(comDirectory+"/matlaboutput.txt");
    if( !matlabfile.open( QIODevice::ReadOnly ) ) {
        qDebug() << QString("Output file could not be opened");
        return;
    }
    matlabfile.seek(numCharRead);

    QScrollBar *bar = verticalScrollBar();
    bar->setValue(bar->maximum());

    QByteArray line;

    processOutputStream << line;
    //Pick out complete lines from the input stream
    //and search for stateScript messages
    bool moreLinesLeft = true;
    while (moreLinesLeft) {

        line = matlabfile.readLine(1024);
        insertPlainText(QString(line));
        numCharRead = matlabfile.pos();


        if (line.isEmpty()) {
            moreLinesLeft = false;
        } else {
            QString tmpLine = QString(line);
            if (tmpLine.contains("SCQTMESSAGE: ")) {
                //If the line has the magic header, cut out the message and emit.
                int messageStartLoc = tmpLine.indexOf("SCQTMESSAGE: ") + 13;
                tmpLine.remove(0,messageStartLoc);
                tmpLine.append("\n");
                //qDebug() << "New message received: " << tmpLine;
                emit stateScriptCommandReceived(tmpLine);
            }
        }
    }

     matlabfile.close();
}


