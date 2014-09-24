#!/bin/env python

import sys
import imp
import copy
import os
import shutil
import pickle
import math
from CMGTools.Production.batchmanager import BatchManager

def chunks(l, n):
    return [l[i:i+n] for i in range(0, len(l), n)]

def split(comps):
    # import pdb; pdb.set_trace()
    splitComps = []
    for comp in comps:
        if hasattr( comp, 'splitFactor') and comp.splitFactor>1:
            chunkSize = len(comp.files) / comp.splitFactor
            if len(comp.files) % comp.splitFactor:
                chunkSize += 1
            # print 'chunk size',chunkSize, len(comp.files), comp.splitFactor
            for ichunk, chunk in enumerate( chunks( comp.files, chunkSize)):
                newComp = copy.deepcopy(comp)
                newComp.files = chunk
                newComp.name = '{name}_Chunk{index}'.format(name=newComp.name,
                                                       index=ichunk)
                splitComps.append( newComp )
        else:
            splitComps.append( comp )
    return splitComps


def batchScriptCERN( index, remoteDir=''):
   '''prepare the LSF version of the batch script, to run on LSF'''
   script = """#!/bin/bash
#BSUB -q 8nm
echo 'environment:'
echo
env
# ulimit -v 3000000 # NO
echo 'copying job dir to worker'
cd $CMSSW_BASE/src
eval `scramv1 ru -sh`
# cd $LS_SUBCWD
# eval `scramv1 ru -sh`
cd -
cp -rf $LS_SUBCWD .
ls
cd `find . -type d | grep /`
echo 'running'
python $CMSSW_BASE/src/CMGTools/RootTools/python/fwlite/Looper.py config.pck
echo
echo 'sending the job directory back'
cp -r Loop/* $LS_SUBCWD
"""
   return script

def batchScriptDESY( jobDir='/nfs/dust/cms/user/lobanov/SUSY/Run2/CMG/CMSSW_7_0_6_patch1/src/CMGTools/TTHAnalysis/cfg/output_Directory/TTJets_PU20bx25_V52'):
   '''prepare the NAF version of the batch script, to run on NAF'''
   script = """#!/bin/bash
## make sure the right shell will be used
#$ -S /bin/zsh
## the cpu time for this job
#$ -l h_rt=02:59:00
## the maximum memory usage of this job
#$ -l h_vmem=1900M
## operating system
##$ -l distro=sld5
## architecture
##$ -l arch=amd64
## stderr and stdout are merged together to stdout
#$ -j y
##(send mail on job's end and abort)
##$ -m a
#$ -l site=hh
## define outputdir,executable,config file and LD_LIBRARY_PATH
#$ -v OUTDIR="""

   script += jobDir
   script += """
##$ -v OUTDIR=/afs/desy.de/user/l/lobanov/calib/Batch/
## define dir for stdout
#$ -o """

   script += jobDir
   script += """/logs"""
   script += """
##$ -o /afs/desy.de/user/l/lobanov/calib/Batch/Output

#start of script
echo job start at `date`

#echo 'copying job dir to worker'
cd $CMSSW_BASE/src
eval `scramv1 ru -sh`
# cd $LS_SUBCWD
# eval `scramv1 ru -sh`
cd $OUTDIR
jobID=$SGE_TASK_ID
cd *_Chunk$jobID

echo 'running in dir' `pwd`
python $CMSSW_BASE/src/CMGTools/RootTools/python/fwlite/Looper.py config.pck
echo
echo 'sending the job directory back'
"""
   return script

def batchScriptLocal(  remoteDir, index ):
   '''prepare a local version of the batch script, to run using nohup'''

   script = """#!/bin/bash
echo 'running'
python $CMSSW_BASE/src/CMGTools/RootTools/python/fwlite/Looper.py config.pck
echo
echo 'sending the job directory back'
mv Loop/* ./
"""
   return script



class MyBatchManager( BatchManager ):
   '''Batch manager specific to cmsRun processes.'''

   def PrepareJobUser(self, jobDir, value ):
       '''Prepare one job. This function is called by the base class.'''
       print value
       print components[value]

       #prepare the batch script
       outputDir = self.outputDir_
       scriptFileName = outputDir+'/batchScript.sh'
       if not os.path.isfile(scriptFileName):
           scriptFile = open(scriptFileName,'w')
           storeDir = self.remoteOutputDir_.replace('/castor/cern.ch/cms','')
           print 'options are', options.batch
           mode = self.RunningMode(options.batch)

           if mode == 'LXPLUS':
               scriptFile.write( batchScriptCERN( storeDir, value) )
           if mode == 'NAF':
               scriptFile.write( batchScriptDESY( outputDir ) )
           elif mode == 'LOCAL':
               scriptFile.write( batchScriptLocal( storeDir, value) )

           scriptFile.close()
           os.system('chmod +x %s' % scriptFileName)

       shutil.copyfile(cfgFileName, jobDir+'/pycfg.py')
       jobConfig = copy.deepcopy(config)
       jobConfig.components = [ components[value] ]
       cfgFile = open(jobDir+'/config.pck','w')
       pickle.dump( jobConfig, cfgFile )
       # pickle.dump( cfo, cfgFile )
       cfgFile.close()

   def SubmitJobArray(self, numbOfJobs):
       '''Submit all jobs as an array.'''
#       numbOfJobs = len(components)
       outputDir = self.outputDir_
#       outputDir = self.options_.outputDir
       print 'Number of jobs', numbOfJobs
       print 'Outputdir', outputDir

       self.mkdir(outputDir+"/logs")

       subline = self.options_.batch
       subline =  subline.replace("-t","-t 1-"+str(numbOfJobs))
       subline =  subline.replace("batchScript.sh",outputDir+"/batchScript.sh")
       print subline

       os.chdir( outputDir )
       os.system( subline )

if __name__ == '__main__':
    batchManager = MyBatchManager()
    batchManager.parser_.usage="""
    %prog [options] <cfgFile>

    Run Colin's python analysis system on the batch.
    Job splitting is determined by your configuration file.
    """

    options, args = batchManager.ParseOptions()

    cfgFileName = args[0]

    handle = open(cfgFileName, 'r')
    cfo = imp.load_source("pycfg", cfgFileName, handle)
    config = cfo.config
    handle.close()

    components = split( [comp for comp in config.components if len(comp.files)>0] )
    listOfValues = range(0, len(components))
    listOfNames = [comp.name for comp in components]

    print 'Preparing my jobs'
    batchManager.PrepareJobs( listOfValues, listOfNames )

    if '-t' not in options.batch:
        waitingTime = 0.1
        batchManager.SubmitJobs( waitingTime )
    else:
        print 'Submittinh job array'
        batchManager.SubmitJobArray(len(listOfNames))
