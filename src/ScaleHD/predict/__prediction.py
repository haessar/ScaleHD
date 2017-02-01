from __future__ import division

#/usr/bin/python
__version__ = 0.01
__author__ = 'alastair.maxwell@glasgow.ac.uk'

##
## Generic imports
import os
import csv
import peakutils
import matplotlib
import numpy as np
import pandas as pd
matplotlib.use('Agg')
import logging as log
from sklearn import svm
import matplotlib.pyplot as plt
from collections import Counter
from sklearn import preprocessing
from peakutils.plot import plot as pplot
from matplotlib.patches import Rectangle
from sklearn.multiclass import OutputCodeClassifier

##
## Backend Junk
from ..__backend import DataLoader
from ..__backend import Colour as clr

class AlleleGenotyping:
	def __init__(self, sequencepair_object, allele_object, instance_params, training_data):

		##
		## Allele objects and instance data
		self.sequencepair_object = sequencepair_object
		self.allele_object = allele_object
		self.instance_params = instance_params
		self.training_data = training_data
		self.allele_report = ''

		##
		## If current allele object assembly/distro is blank
		## Allele is typical, didn't assign in __atypical.py
		## Hence, assign allele with sequencepair_object values
		if not allele_object.get_rvdist():
			allele_object.set_fwassembly(sequencepair_object.get_fwassembly())
			allele_object.set_rvassembly(sequencepair_object.get_rvassembly())
			allele_object.set_fwdist(sequencepair_object.get_fwdist())
			allele_object.set_rvdist(sequencepair_object.get_rvdist())

		##
		## Build a classifier and class label hash-encoder for CCG SVM
		self.classifier, self.encoder = self.build_zygosity_model()

		##
		## Information and error flags for this allele
		self.allele_flags = {'FlagsTODO':True}

		##
		## Unlablled distribution to utilise for SVM prediction
		print 'fw: ', allele_object.get_fwdist()
		print 'rv: ', allele_object.get_rvdist()
		self.forward_distribution = self.scrape_distro(allele_object.get_fwdist())
		self.reverse_distribution = self.scrape_distro(allele_object.get_rvdist())

		##
		## Constructs
		self.zygosity_state = None; self.forwardccg_aggregate = None; self.reverseccg_aggregate = None

		##
		## Genotype!!
		self.main()

	def main(self):

		###############################
		## Stage one -- CCG Zygosity ##
		###############################
		print '>>Stage one'
		self.forwardccg_aggregate = self.distribution_collapse(self.forward_distribution)
		self.reverseccg_aggregate = self.distribution_collapse(self.reverse_distribution)
		self.zygosity_state = self.predict_zygstate()

		############################
		## Stage two -- CCG Peaks ##
		############################
		print '>> Stage two'

		######################################
		## Stage three -- CAG Investigation ##
		######################################
		print '>> Stage three'

		####################################
		## Stage four -- Ensure integrity ##
		####################################
		print '>> Stage four'

		##########################################
		## Stage five -- Mosaicism calculations ##
		##########################################
		print '>> Stage five'

		##############################################
		## Stage six -- Caluclate allele confidence ##
		##############################################
		print '>> Stage six'

	def build_zygosity_model(self):
		"""
		Function to build a SVM (wrapped into OvO class) for determining CCG zygosity
		:return: svm object wrapped into OvO, class-label hash-encoder object
		"""

		##
		## Classifier object and relevant parameters for our CCG prediction
		svc_object = svm.LinearSVC(C=1.0, loss='ovr', penalty='l2', dual=False,
								   tol=1e-4, multi_class='crammer_singer', fit_intercept=True,
								   intercept_scaling=1, verbose=0, random_state=0, max_iter=-1)

		##
		## Take raw training data (CCG zygosity data) into DataLoader model object
		traindat_ccg_collapsed = self.training_data['CollapsedCCGZygosity']
		traindat_descriptionfi = self.training_data['GenericDescriptor']
		traindat_model = DataLoader(traindat_ccg_collapsed, traindat_descriptionfi).load_model()

		##
		## Model data fitting to SVM
		X = preprocessing.normalize(traindat_model.DATA)
		Y = traindat_model.TARGET
		ovo_svc = OutputCodeClassifier(svc_object, code_size=2, random_state=0).fit(X,Y)
		encoder = traindat_model.ENCDR

		##
		## Return the fitted OvO(SVM) and Encoder
		return ovo_svc, encoder

	def predict_zygstate(self):
		"""
		Function which takes the newly collapsed CCG distribution and executes SVM prediction
		to determine the zygosity state of this sample's CCG value(s). Data is reshaped
		and normalised to ensure more reliable results. A check is executed between the results of
		forward and reverse zygosity; if a match, great; if not, not explicitly bad but inform user.
		:return: zygosity[2:-2] (trimming unrequired characters)
		"""

		##
		## Reshape the input distribution so SKL doesn't complain about 1D vectors
		## Normalise data in addition; cast to float64 for this to be permitted
		forward_reshape = preprocessing.normalize(np.float64(self.forwardccg_aggregate.reshape(1,-1)))
		reverse_reshape = preprocessing.normalize(np.float64(self.reverseccg_aggregate.reshape(1,-1)))

		##
		## Predict the zygstate of these reshapen, noramlised 20D CCG arrays using SVM object earlier
		## Results from self.classifier are #encoded; so convert with our self.encoder.inverse_transform
		forward_zygstate = str(self.encoder.inverse_transform(self.classifier.predict(forward_reshape)))
		reverse_zygstate = str(self.encoder.inverse_transform(self.classifier.predict(reverse_reshape)))

		##
		## We only particularly care about the reverse zygosity (CCG reads are higher quality in reverse data)
		## However, for a QoL metric, compare fw/rv results. If match, good! If not, who cares!
		if not forward_zygstate == reverse_zygstate: self.allele_flags['CCGZygDisconnect'] = True
		else: self.allele_flags['CCGZyg_disconnect'] = False
		return reverse_zygstate[2:-2]

	@staticmethod
	def scrape_distro(distributionfi):
		"""
		Function to take the aligned read-count distribution from CSV into a numpy array
		:param distributionfi:
		:return: np.array(data_from_csv_file)
		"""

		##
		## Open CSV file with information within; append to temp list
		## Scrape information, cast to np.array(), return
		placeholder_array = []
		with open(distributionfi) as dfi:
			source = csv.reader(dfi, delimiter=',')
			next(source) #skip header
			for row in source:
				placeholder_array.append(int(row[2]))
			dfi.close()
		unlabelled_distro = np.array(placeholder_array)
		return unlabelled_distro

	@staticmethod
	def distribution_collapse(distribution_array):
		"""
		Function to take a full 200x20 array (struc: CAG1-200,CCG1 -- CAG1-200CCG2 -- etc CCG20)
		and aggregate all CAG values for each CCG
		:param distribution_array: input dist (should be (1-200,1-20))
		:return: 1x20D np(array)
		"""

		##
		## Object for CCG split
		ccg_arrays = None

		##
		## Hopefully the user has aligned to the right reference dimensions
		try: ccg_arrays = np.split(distribution_array, 20)
		except ValueError: raise Exception('Input reads individisible by 20. Utilised incorrect reference style.')

		##
		## Aggregate each CCG
		ccg_counter = 1
		collapsed_array = []
		for ccg_array in ccg_arrays:
			collapsed_array.append(np.sum(ccg_array))
			ccg_counter+=1

		print '$DBG: Inner distro collapse'
		print collapsed_array

		return np.asarray(collapsed_array)

	def get_report(self):
		return self.allele_report

class GenotypePrediction:
	def __init__(self, data_pair, prediction_path, training_data, instance_params, processed_atypical):
		"""
		Prediction stage of the pipeline -- use of SVM, density estimation and first order differentials.
		Automates calling of sample's genotype based on data information dervied from aligned read counts.
		Utilises forward reads for CAG information, reverse reads for CCG information. Combine for genotype.

		General workflow overview:
		--Take reverse reads, aggregate every CAG for each CCG bin
		--Use unlabelled sample into CCG zygosity SVM for het/hom prediction
		--Data cleaning/normalisation/etc
		--Two Pass algorithm to determine genotype
		--1) Density Estimation on distribution to gauge where the peaks may be/peak distances
		--2) Peak Detection via first order differentials, taking into account density results for tailoring
		--Repeat process for relevant CAG distribution(s) taking CCG het/hom into account
		--Return genotype

		:param data_pair: Files to be used for scraping
		:param prediction_path: Output path to save all resultant files from this process
		:param training_data: Data to be used in building CCG SVM model
		:param instance_params: redundant parameters--unused in this build
		:param processed_atypical: any atypical allele information processed
		"""

		##
		## Paths and files to be used in this instance
		self.data_pair = data_pair
		self.prediction_path = prediction_path
		self.training_data = training_data
		self.instance_params = instance_params
		self.processed_atypicals = processed_atypical

		##
		## Build a classifier and class label hash-encoder for CCG SVM
		self.classifier, self.encoder = self.build_zygosity_model()

		##
		## Information and error flags for this instance
		## For explanations of the flags; check documentation
		self.prediction_confidence = 0
		self.cag_intermediate = [0,0]
		self.genotype_flags = {'PrimaryAllele':[0,0], 'SecondaryAllele':[0,0], 'PrimaryMosaicism':[],
							   'SecondaryMosaicism':[], 'ThresholdUsed':0, 'RecallCount':0,
							   'LowReadDistributions':0, 'AlignmentPadding':False, 'SVMPossibleFailure':False,
							   'PotentialHomozygousHaplotype':False, 'PHHInterpDistance':0.0, 'NeighbouringPeaks':False,
							   'DiminishedPeak':False, 'DiminishedUncertainty':False, 'PeakExpansionSkew':False,
							   'CCGZygDisconnect':False, 'CCGPeakAmbiguous':False, 'CCGDensityAmbiguous':False,
							   'CCGRecallWarning':False, 'CCGPeakOOB':False, 'CAGPeakAmbiguous':False,
							   'CAGDensityAmbiguous':False, 'CAGRecallWarning':False, 'CAGPeakOOB':False,
							   'CAGBackwardsSlippage':False, 'CAGForwardSlippage':False, 'FPSPDisconnect':False,
							   'DSPCorrection':False}

		##
		## Unlabelled distributions to utilise for SVM prediction
		## Padded distro = None, in case where SAM aligned to (0-100,0-20 NOT 1-200,1-20), use this
		self.forward_distribution = np.empty(shape=(1,1)); self.reverse_distribution = np.empty(shape=(1,1))
		if type(self.data_pair[0]) == str:
			self.forward_distribution = self.scrape_distro(self.data_pair[0])
			self.reverse_distribution = self.scrape_distro(self.data_pair[1])
		if type(self.data_pair[1]) == tuple:
			self.forward_distribution = self.scrape_distro(self.data_pair[0][0])
			self.reverse_distribution = self.scrape_distro(self.data_pair[1][0])

		self.forwardccg_aggregate = None; self.reverseccg_aggregate = None
		self.forward_distr_padded = None; self.zygosity_state = None
		self.gtype_report = None

		##
		## Run the code
		self.main()

	def main(self):
		"""
		Main function of this 'object' which calls on other functions/classes to determine a genotype
		Each sample is broken down into stages, to simplify the search space of possible genotypes.
		:return: None
		"""

		##
		## >> Stage one -- Determine zygosity of CCG from input distro
		## - Aggregate CCG reads from 200x20 to 1x20; feed into SVM
		## - Compare results between forward and reverse (reverse takes priorty)
		self.forwardccg_aggregate = self.distribution_collapse(self.forward_distribution, st=True)
		self.reverseccg_aggregate = self.distribution_collapse(self.reverse_distribution)
		self.zygosity_state = self.predict_zygstate()

		##
		## >> Stage two -- Determine CCG Peak(s) via 2Pass Algorithm
		## If a failure occurs, a re-call continues until attempts exhausted
		ccg_failstate, ccg_genotype = self.determine_ccg_genotype()
		while ccg_failstate:
			self.genotype_flags['CCGRecallWarning'] = True
			ccg_failstate, ccg_genotype = self.determine_ccg_genotype(threshold_bias=True)

		self.genotype_flags['PrimaryAllele'][1] = ccg_genotype[0]
		self.genotype_flags['SecondaryAllele'][1] = ccg_genotype[1]

		##
		## >> Stage three -- Investigate respective CAG distributions for our CCG peaks
		## Once determined, CAG and CCG are combined to create an allele's genotype
		cag_failstate, cag_genotype = self.determine_cag_genotype()
		while cag_failstate:
			self.genotype_flags['CAGRecallWarning'] = True
			cag_failstate, cag_genotype = self.determine_cag_genotype(threshold_bias=True)

		self.genotype_flags['PrimaryAllele'][0] = cag_genotype[0]
		self.genotype_flags['SecondaryAllele'][0] = cag_genotype[1]

		##
		## Ensure normal/expanded alleles are in the correct index (i.e. higher CAG == expanded)
		if int(self.genotype_flags['PrimaryAllele'][0]) > int(self.genotype_flags['SecondaryAllele'][0]):
			intermediate = self.genotype_flags['PrimaryAllele']
			self.genotype_flags['PrimaryAllele'] = self.genotype_flags['SecondaryAllele']
			self.genotype_flags['SecondaryAllele'] = intermediate

		##
		## >> Stage four -- Simple somatic mosaicism calculations
		self.genotype_flags['PrimaryMosaicism'] = self.somatic_calculations(self.genotype_flags['PrimaryAllele'])
		self.genotype_flags['SecondaryMosaicism'] = self.somatic_calculations(self.genotype_flags['SecondaryAllele'])

		##
		## >> Stage five -- Calculate confidence in genotype, report
		self.append_atypicals()
		self.confidence_calculation()
		self.gtype_report = self.generate_report()

	def build_zygosity_model(self):
		"""
		Function to build a SVM (wrapped into OvO class) for determining CCG zygosity
		:return: svm object wrapped into OvO, class-label hash-encoder object
		"""

		##
		## Classifier object and relevant parameters for our CCG prediction
		svc_object = svm.LinearSVC(C=1.0, loss='ovr', penalty='l2', dual=False,
								   tol=1e-4, multi_class='crammer_singer', fit_intercept=True,
								   intercept_scaling=1, verbose=0, random_state=0, max_iter=-1)

		##
		## Take raw training data (CCG zygosity data) into DataLoader model object
		traindat_ccg_collapsed = self.training_data['CollapsedCCGZygosity']
		traindat_descriptionfi = self.training_data['GenericDescriptor']
		traindat_model = DataLoader(traindat_ccg_collapsed, traindat_descriptionfi).load_model()

		##
		## Model data fitting to SVM
		X = preprocessing.normalize(traindat_model.DATA)
		Y = traindat_model.TARGET
		ovo_svc = OutputCodeClassifier(svc_object, code_size=2, random_state=0).fit(X,Y)
		encoder = traindat_model.ENCDR

		##
		## Return the fitted OvO(SVM) and Encoder
		return ovo_svc, encoder

	@staticmethod
	def scrape_distro(distributionfi):
		"""
		Function to take the aligned read-count distribution from CSV into a numpy array
		:param distributionfi:
		:return: np.array(data_from_csv_file)
		"""

		##
		## Open CSV file with information within; append to temp list
		## Scrape information, cast to np.array(), return
		placeholder_array = []
		with open(distributionfi) as dfi:
			source = csv.reader(dfi, delimiter=',')
			next(source) #skip header
			for row in source:
				placeholder_array.append(int(row[2]))
			dfi.close()
		unlabelled_distro = np.array(placeholder_array)
		return unlabelled_distro

	def distribution_collapse(self, distribution_array, st=False):
		"""
		Function to take a full 200x20 array (struc: CAG1-200,CCG1 -- CAG1-200CCG2 -- etc CCG20)
		and aggregate all CAG values for each CCG
		:param distribution_array: input dist (should be (1-200,1-20))
		:param st: flag for if we're in forward stage; i.e. input aligned to wrong ref -> assign padded to fwrd
		:return: 1x20D np(array)
		"""

		##
		## Object for CCG split
		ccg_arrays = None

		##
		## Hopefully the user has aligned to the right reference dimensions
		## Check.. if not, hopefully we can pad (and raise flag.. since it is not ideal)
		try:
			ccg_arrays = np.split(distribution_array, 20)
		##
		## User aligned to the wrong reference..
		except ValueError:
			self.genotype_flags['AlignmentPadding'] = True

			##
			## If the distro is this size, they aligned to (0-100,0-20)...
			## Split by 21, append with 99x1's to end of each CCG
			## Trim first entry in new list (CCG0.. lol who even studies that)
			## If we're on a forward distro collapse, assign padded distro (for mosaicism later)
			if len(distribution_array) == 2121:
				altref_split = np.split(distribution_array, 21)
				padded_split = []
				for ccg in altref_split:
					current_pad = np.append(ccg[1:], np.ones(100))
					padded_split.append(current_pad)
				ccg_arrays = padded_split[1:]

				if st:
					self.forward_distr_padded = np.asarray([item for sublist in ccg_arrays for item in sublist])

		##
		## Aggregate each CCG
		ccg_counter = 1
		collapsed_array = []
		for ccg_array in ccg_arrays:
			collapsed_array.append(np.sum(ccg_array))
			ccg_counter+=1
		return np.asarray(collapsed_array)

	def predict_zygstate(self):
		"""
		Function which takes the newly collapsed CCG distribution and executes SVM prediction
		to determine the zygosity state of this sample's CCG value(s). Data is reshaped
		and normalised to ensure more reliable results. A check is executed between the results of
		forward and reverse zygosity; if a match, great; if not, not explicitly bad but inform user.
		:return: zygosity[2:-2] (trimming unrequired characters)
		"""

		##
		## Reshape the input distribution so SKL doesn't complain about 1D vectors
		## Normalise data in addition; cast to float64 for this to be permitted
		forward_reshape = preprocessing.normalize(np.float64(self.forwardccg_aggregate.reshape(1,-1)))
		reverse_reshape = preprocessing.normalize(np.float64(self.reverseccg_aggregate.reshape(1,-1)))

		##
		## Predict the zygstate of these reshapen, noramlised 20D CCG arrays using SVM object earlier
		## Results from self.classifier are #encoded; so convert with our self.encoder.inverse_transform
		forward_zygstate = str(self.encoder.inverse_transform(self.classifier.predict(forward_reshape)))
		reverse_zygstate = str(self.encoder.inverse_transform(self.classifier.predict(reverse_reshape)))

		##
		## We only particularly care about the reverse zygosity (CCG reads are higher quality in reverse data)
		## However, for a QoL metric, compare fw/rv results. If match, good! If not, who cares!
		if not forward_zygstate == reverse_zygstate:
			self.genotype_flags['CCGZygDisconnect'] = True
		else:
			self.genotype_flags['CCGZyg_disconnect'] = False
		return reverse_zygstate[2:-2]

	def update_flags(self, target_updates):
		"""
		Function that will take a list of flags that were raised from the 2-Pass algorithm
		and update this pipeline's instance of self.genotype_flags accordingly.
		This allows us to keep a current state-of-play of this sample's prediction.
		:param target_updates: List of flags from the 2-Pass algorithm
		:return: None
		"""

		for update_key, update_value in target_updates.iteritems():
			for initial_key, initial_value in self.genotype_flags.iteritems():
				if initial_key == update_key:
					self.genotype_flags[initial_key] = update_value

	def determine_ccg_genotype(self, fail_state=False, threshold_bias=False):
		"""
		Function to determine the genotype of this sample's CCG alleles
		Ideally this function will be called one time, but where exceptions occur
		it may be re-called with a lower quality threshold -- inform user when this occurs
		:param fail_state: optional flag for re-calling when a previous call failed
		:param threshold_bias: optional flag for lowering FOD threshold when a previous called failed
		:return: failure state, CCG genotype data ([None,X],[None,Y])
		"""

		##
		## We're going to be paranoid and bootstrap a check on the zygstate call
		def paranoia(input_dist):
			## Top1/2 for CCG (top3 not applicable)
			major_estimate = max(input_dist)
			minor_estimate = max(n for n in input_dist if n!=major_estimate)
			## percentage drop from maj to min
			literal_drop = (abs(major_estimate-minor_estimate) / major_estimate) * 100

			## if minor is 60% of major, or less, maybe we are het and the SVM was wrong
			if minor_estimate < 1000:
				if literal_drop <= 60.00:
					self.genotype_flags['SVMPossibleFailure'] = True
					self.zygosity_state = 'HETERO'
					return 2
				else:
					self.zygosity_state = 'HOMO'
					return 1
			else:
				if literal_drop <= 85.00:
					self.genotype_flags['SVMPossibleFailure'] = True
					self.zygosity_state = 'HETERO'
					return 2
				else:
					self.zygosity_state = 'HOMO'
					return 1
		peak_target = 0
		if self.zygosity_state == 'HOMO': peak_target = 1
		if self.zygosity_state == 'HETERO': peak_target = 2
		if peak_target == 1: peak_target = paranoia(self.reverseccg_aggregate)

		##
		## Create object for 2-Pass algorithm to use with CCG
		graph_parameters = [20, 'CCGDensityEstimation.pdf', 'CCG Density Distribution', ['Read Count', 'Bin Density']]
		ccg_inspector = SequenceTwoPass(prediction_path=self.prediction_path,
										input_distribution=self.reverseccg_aggregate,
										peak_target=peak_target,
										graph_parameters=graph_parameters,
										zygosity_state = self.zygosity_state,
										contig_stage='CCG')

		"""
		!! Sub-Stage one !!
		Now that we've made an object with the settings for this instance..
		Density estimation of the CCG distribution..
		Get warnings encountered by this instance of SequenceTwoPass
		Update equivalent warning flags within GenotypePrediction
		"""
		first_pass = ccg_inspector.density_estimation(plot_flag=True)
		density_warnings = ccg_inspector.get_warnings()
		self.update_flags(density_warnings)

		"""
		!! Sub-Stage two !!
		Now we have our estimates from the KDE sub-stage, we can use these findings
		in our FOD peak identification for more specific peak calling and thus, genotyping
		"""
		fod_param = [[0,20,21],'CCG Peaks',['CCG Value', 'Read Count'], 'CCGPeakDetection.pdf']
		fod_failstate, second_pass = ccg_inspector.differential_peaks(first_pass, fod_param, threshold_bias)
		while fod_failstate:
			fod_failstate, second_pass = ccg_inspector.differential_peaks(first_pass, fod_param, threshold_bias, fod_recall=True)
		differential_warnings = ccg_inspector.get_warnings()
		self.update_flags(differential_warnings)

		##
		## Check if First Pass Estimates == Second Pass Results
		## If there is a mismatch, genotype calling has failed and thus re-call will be required
		first_pass_estimate = [first_pass['PrimaryPeak'],first_pass['SecondaryPeak']]
		second_pass_estimate = [second_pass['PrimaryPeak'], second_pass['SecondaryPeak']]

		if not first_pass_estimate == second_pass_estimate or len(second_pass_estimate)>len(first_pass_estimate):
			self.genotype_flags['FPSPDisconnect'] = True
			fail_state = True

		##
		## Return whether this process passed or not, and the genotype
		return fail_state, second_pass_estimate

	@staticmethod
	def split_cag_target(input_distribution, ccg_target):
		"""
		Function to gather the relevant CAG distribution for the specified CCG value
		We gather this information from the forward distribution of this sample pair as CCG reads are
		of higher quality in the forward sequencing direction.
		We split the entire fw_dist into contigs/bins for each CCG (4000 -> 200*20)
		:param input_distribution: input forward distribution (4000d)
		:param ccg_target: target value we want to select the 200 values for
		:return: the sliced CAG distribution for our specified CCG value
		"""

		cag_split = [input_distribution[i:i+200] for i in xrange(0, len(input_distribution), 200)]
		distribution_dict = {}
		for i in range(0, len(cag_split)):
			distribution_dict['CCG'+str(i+1)] = cag_split[i]

		current_target_distribution = distribution_dict['CCG' + str(ccg_target)]
		return current_target_distribution

	def determine_cag_genotype(self, fail_state=False, threshold_bias=False):
		"""
		Function to determine the genotype of this sample's CAG alleles
		Ideally this function will be called one time, but where exceptions occur,
		it may be re-caled with a lower quality-threshold -- inform user when this occurs

		If CCG was homozygous (i.e. one CCG distro) -- there will be 2 CAG peaks to investigate
		If CCG was heterozygous (i.e. two CCG distro) -- there will be 1 CAG peak in each CCG to investigate

		:param fail_state: optional flag for re-calling when a previous call failed
		:param threshold_bias: optional flag for lowering FOD threshold when a previous call failed
		:return: failure state, CAG genotype data ([X,None],[Y,None])
		"""

		##
		## Check for padding status
		## If user aligned to wrong reference, we need to use self.forward_distr_padded instead of
		## self.forward_distribution; otherwise dimensionality is incorrect...

		if not self.genotype_flags['AlignmentPadding']: forward_utilisation = self.forward_distribution
		else: forward_utilisation = self.forward_distr_padded

		##
		## Set up distributions we require to investigate
		## If Homozygous, we have one CCG distribution that will contain 2 CAG peaks to investigate
		## If Heterozygous, we have two CCG distributions, each with 1 CAG peak to investigate
		peak_target = 0
		target_distribution = {}
		if self.zygosity_state == 'HOMO':
			peak_target = 2
			cag_target = self.split_cag_target(forward_utilisation, self.genotype_flags['PrimaryAllele'][1])
			target_distribution[self.genotype_flags['PrimaryAllele'][1]] = cag_target
		if self.zygosity_state == 'HETERO':
			peak_target = 1
			cag_target_major = self.split_cag_target(forward_utilisation, self.genotype_flags['PrimaryAllele'][1])
			cag_target_minor = self.split_cag_target(forward_utilisation, self.genotype_flags['SecondaryAllele'][1])
			target_distribution[self.genotype_flags['PrimaryAllele'][1]] = cag_target_major
			target_distribution[self.genotype_flags['SecondaryAllele'][1]] = cag_target_minor

		##
		## Now iterate over our scraped distributions with our 2 pass algorithm
		for cag_key, distro_value in target_distribution.iteritems():

			##
			## If the amount of reads in this distro is super low
			## Increment flag, which will be used later in confidence score
			if sum(list(distro_value)) < 1500:
				self.genotype_flags['LowReadDistributions'] += 1

			##
			## Generate KDE graph parameters
			## Generate CAG inspector Object for 2Pass-Algorithm
			graph_parameters = [200, '{}{}{}'.format('CAG',str(cag_key),'DensityEstimation.pdf'), 'CAG Density Distribution', ['Read Count', 'Bin Density']]
			cag_inspector = SequenceTwoPass(prediction_path=self.prediction_path,
											input_distribution=distro_value,
											peak_target=peak_target,
											graph_parameters=graph_parameters,
											zygosity_state=self.zygosity_state,
											contig_stage='CAG')

			"""
			!! Sub-stage one !!
			Now that we've made an object with the settings for this instance..
			Density estimation of the CCG distribution..
			Get warnings encountered by this instance of SequenceTwoPass
			Update equivalent warning flags within GenotypePrediction
			"""
			first_pass = cag_inspector.density_estimation(plot_flag=True)
			density_warnings = cag_inspector.get_warnings()
			self.update_flags(density_warnings)

			"""
			!! Sub-stage two !!
			Now we have our estimates from the KDE sub-stage, we can use these findings
			in our FOD peak identification for more specific peak calling and thus, genotyping
			"""
			fod_param = [[0,200,201],'{}{})'.format('CAG Peaks (CCG',str(cag_key)),['CAG Value', 'Read Count'], '{}{}{}'.format('CCG',str(cag_key),'-CAGPeakDetection.pdf')]
			fod_failstate, second_pass = cag_inspector.differential_peaks(first_pass, fod_param, threshold_bias)
			while fod_failstate:
				fod_failstate, second_pass = cag_inspector.differential_peaks(first_pass, fod_param, threshold_bias, fod_recall=True)
			differential_warnings = cag_inspector.get_warnings()
			self.update_flags(differential_warnings)

			##
			## Concatenate results into a sample-wide genotype format
			first_pass_estimate = [first_pass['PrimaryPeak'], first_pass['SecondaryPeak']]
			second_pass_estimate = [second_pass['PrimaryPeak'], second_pass['SecondaryPeak']]

			if not first_pass_estimate == second_pass_estimate or len(second_pass_estimate)>len(first_pass_estimate):
				self.genotype_flags['FPSPDisconnect'] = True
				fail_state = True

			##
			## Ensure the correct CAG is assigned to the appropriate CCG
			if self.zygosity_state == 'HOMO':
				if cag_key == self.genotype_flags['PrimaryAllele'][1]:
					self.cag_intermediate[0] = second_pass_estimate[0]
					self.cag_intermediate[1] = second_pass_estimate[1]
			if self.zygosity_state == 'HETERO':
				if cag_key == self.genotype_flags['PrimaryAllele'][1]:
					self.cag_intermediate[0] = second_pass_estimate[0]
				if cag_key == self.genotype_flags['SecondaryAllele'][1]:
					self.cag_intermediate[1] = second_pass_estimate[0]

		##
		## Generate object and return
		cag_genotype = [self.cag_intermediate[0],self.cag_intermediate[1]]
		return fail_state, cag_genotype

	def somatic_calculations(self, genotype):
		"""
		Function for basic somatic mosaicism calculations; featureset will be expanded upon later
		For now; N-1 / N, N+1 / N calculations are executed on arranged contigs where the N value is known
		(from genotype prediction -- assumed to be correct)
		In addition, the read count distribution for the forward and reverse reads in a sample pair are both
		aligned so that their N value is in the same position; lets end-user investigate manual distribution
		data quality etc.
		:param genotype: value of predicted genotype from the SVM/2PA stages of GenotypePrediction()
		:return: mosaicism_values; results of simple sommos calculations :))))))
		"""

		##
		## Create mosaicism investigator object to begin calculation prep
		## Takes raw 200x20 dist and slices into 20 discrete 200d arrays
		## Orders into a dataframe with CCG<val> labels
		## Scrapes appropriate values for SomMos calculations
		if not self.genotype_flags['AlignmentPadding']:
			mosaicism_object = MosaicismInvestigator(genotype, self.forward_distribution)
		else:
			mosaicism_object = MosaicismInvestigator(genotype, self.forward_distr_padded)
		ccg_slices = mosaicism_object.chunks(200)
		ccg_ordered = mosaicism_object.arrange_chunks(ccg_slices)
		allele_values = mosaicism_object.get_nvals(ccg_ordered, genotype)

		##
		## With these values, we can calculate and return
		allele_calcs = mosaicism_object.calculate_mosaicism(allele_values)

		##
		## Generate a padded distribution (aligned to N=GTYPE)
		padded_distro = mosaicism_object.distribution_padder(ccg_ordered, genotype)

		##
		## Combine calculation dictionary and distribution into object, return
		## TODO rework padded distributions?
		mosaicism_values = [allele_calcs, padded_distro]
		return mosaicism_values

	def append_atypicals(self):

		"""
		Match SVM and DSP alleles, check for slippage
		TODO: rewrite this pile of dumpster shit
		:return:
		"""

		mismatch_flag = False
		for dsp_allele in self.processed_atypicals:
			if self.genotype_flags['PrimaryAllele'][0] == dsp_allele['EstimatedCAG'] and self.genotype_flags['PrimaryAllele'][1] == dsp_allele['EstimatedCCG']:
				self.genotype_flags['PrimaryAlleleStatus'] = dsp_allele['Status']
				self.genotype_flags['PrimaryAlleleReference'] = dsp_allele['Reference']
				self.genotype_flags['PrimaryAlleleOriginal'] = dsp_allele['OriginalReference']
				continue
			if self.genotype_flags['SecondaryAllele'][0] == dsp_allele['EstimatedCAG'] and self.genotype_flags['SecondaryAllele'][1] == dsp_allele['EstimatedCCG']:
				self.genotype_flags['SecondaryAlleleStatus'] = dsp_allele['Status']
				self.genotype_flags['SecondaryAlleleReference'] = dsp_allele['Reference']
				self.genotype_flags['SecondaryAlleleOriginal'] = dsp_allele['OriginalReference']
				continue
			if abs(self.genotype_flags['SecondaryAllele'][0] - dsp_allele['EstimatedCAG']) == 1:
				if self.genotype_flags['SecondaryAllele'][0] > dsp_allele['EstimatedCAG']:
					self.genotype_flags['CAGForwardSlippage'] = True
				if self.genotype_flags['SecondaryAllele'][0] < dsp_allele['EstimatedCAG']:
					self.genotype_flags['CAGBackwardsSlippage'] = True
				self.genotype_flags['SecondaryAllele'][0] = dsp_allele['EstimatedCAG']
				self.genotype_flags['DSPCorrection'] = True
			else:
				mismatch_flag = True
				break

		##TODO this
		if mismatch_flag:
			print 'get highest CAG value from self.processed_atypicals'
			print 'lowest = primary, highest = secondary'
			print 'set self.genotype_flags[] for primary and secondary allele'
			print 'set DSP correction to be true'

	def confidence_calculation(self):
		"""
		Function that will calculate a score for confidence in the genotype
		prediction for the current sample being processed...
		Check which flags have been raised throughout the genotyping process
		Weight accordingly, return
		:return: None
		"""
		current_confidence = 100

		"""
		>> Highest severity <<
		If these flags are raised/over a threshold then there
		has probably been a strong effect on the precision and accuracy of
		the genotype prediction.. user should probably manually check results
		"""
		##
		## Check distributions for fucking AWFUL read count
		if self.genotype_flags['LowReadDistributions'] > 0:
			current_confidence -= (35*self.genotype_flags['LowReadDistributions'])

		##
		## Threshold utilisation during FOD peak calling
		if self.genotype_flags['ThresholdUsed'] != 0.5:
			if self.genotype_flags['ThresholdUsed'] < 0.5: current_confidence -= 5
			elif self.genotype_flags['ThresholdUsed'] < 0.3: current_confidence -= 10
			else: current_confidence -= 20
		else: current_confidence += 10

		##
		## Recall count/CAG-CCG specific recall warnings
		if self.genotype_flags['RecallCount'] != 0:
			if self.genotype_flags['RecallCount'] < 3: current_confidence -= 10
			elif self.genotype_flags['RecallCount'] <= 6: current_confidence -= 20
			else: current_confidence -= 30
			if self.genotype_flags['CCGRecallWarning']: current_confidence -= 15
			if self.genotype_flags['CAGRecallWarning']: current_confidence -= 10
		else: current_confidence += 20

		##
		## SVM Possible failure
		if self.genotype_flags['SVMPossibleFailure']: current_confidence -= 30

		##
		## PeakOOB: >2 peaks returned per allele (i.e. results were sliced)
		for peakoob in [self.genotype_flags['CAGPeakOOB'],self.genotype_flags['CCGPeakOOB']]:
			if peakoob is True: current_confidence -= 40

		##
		## Sample wasn't aligned to CAG1-200/CCG1-20.. padded but raises questions...
		if self.genotype_flags['AlignmentPadding']: current_confidence -= 30

		##
		## DSP Correction occurred on SVM results
		if self.genotype_flags['DSPCorrection']: current_confidence -= 25

		"""
		>> Medium severity <<
		If these flags have been raised/over a threshold, then there
		has probably been a mild effect on the precision/accuracy, but not
		necessarily.. Different weights of flags alter the severity outcome..
		"""

		##
		## Homozygous Haplotype detection?
		if self.genotype_flags['PotentialHomozygousHaplotype']:
			current_confidence -= 10
			if self.genotype_flags['PHHInterpDistance'] > 1.0:
				current_confidence -= 5

		##
		## Peaks are neighbouring? (e.g. 16/17)
		if self.genotype_flags['NeighbouringPeaks']: current_confidence -= 10

		##
		## Diminished peak detection (e.g. 40k vs 100)
		if self.genotype_flags['DiminishedPeak']:
			current_confidence -= 25
			if self.genotype_flags['DiminishedUncertainty']: current_confidence -= 10
		else:
			self.genotype_flags['DiminishedUncertainty'] = False

		##
		## Peak / Density ambiguity (only matters if re-call occurred)
		if self.genotype_flags['RecallCount'] != 0:
			if self.genotype_flags['CAGPeakAmbiguous']: current_confidence -= 2.5
			if self.genotype_flags['CCGPeakAmbiguous']: current_confidence -= 20
			if self.genotype_flags['CAGDensityAmbiguous']: current_confidence -= 2.5
			if self.genotype_flags['CCGDensityAmbiguous']: current_confidence -= 15

		"""
		>> Lowest severity <<
		If these flags are raised, it is for information only
		It is highly doubtful that anything encountered here would negatively
		alter the accuracy/precision of a genotype prediction
		"""

		##
		## Slippage
		if self.genotype_flags['CAGBackwardsSlippage']: current_confidence -= 5
		elif self.genotype_flags['CAGForwardSlippage']: current_confidence -= 2
		else: current_confidence += 5

		##
		## Peak Expansion Skew..
		if self.genotype_flags['PeakExpansionSkew']: current_confidence -= 5
		else: current_confidence += 15

		"""
		>> Mosaicism Investigation <<
		Based on how much somatic mosaicism we see around the peaks..
		That could maybe have altered the genotype prediction away from the
		true value and/or altered accuracy/precision
		"""

		##
		## Mosaicism!
		if self.genotype_flags['PrimaryMosaicism'][0]['NMinusOne-Over-N'] > 0.30: current_confidence -= 2.5
		if self.genotype_flags['PrimaryMosaicism'][0]['NPlusOne-Over-N'] > 0.25: current_confidence -= 4.25
		if self.genotype_flags['SecondaryMosaicism'][0]['NMinusOne-Over-N'] > 0.65: current_confidence -= 7.5
		if self.genotype_flags['SecondaryMosaicism'][0]['NPlusOne-Over-N'] > 0.70: current_confidence -= 10

		##
		## With all flags processed; assign confidence score for this instance
		## Limit output to 100%
		self.prediction_confidence = sorted([0, current_confidence, 100])[1]

	def generate_report(self):
		"""
		Function which will, eventually, calculate the confidence score of this genotype prediction
		by taking into account flags raised, and meta-data about the current sample distribution etc
		:return: For now, a list of report flags. eventually, probably a dictionary with more info within
		"""

		##
		## Hideous string based report for individual samples
		## Will get changed at a later date
		sample_name = self.prediction_path.split('/')[-2]
		sample_report_name = os.path.join(self.prediction_path, sample_name+'QuickReport.txt')
		sample_report = '{}: {}\n{}: {}\n{}: {}\n{}: {}%\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n'.format('File Name', sample_name,
												'Primary Allele', self.genotype_flags['PrimaryAllele'],
												'Secondary Allele', self.genotype_flags['SecondaryAllele'],
												'Prediction Confidence', self.prediction_confidence,
												'Threshold Used', self.genotype_flags['ThresholdUsed'],
												'Recall Count', self.genotype_flags['RecallCount'],
												'Alignment Padding', self.genotype_flags['AlignmentPadding'],
												'\nAtypical Flags', '',
												'Primary Allele status', self.genotype_flags['PrimaryAlleleStatus'],
												'Primary Allele reference', self.genotype_flags['PrimaryAlleleReference'],
												'Primary Allele original', self.genotype_flags['PrimaryAlleleOriginal'],
												'Secondary Allele status', self.genotype_flags['SecondaryAlleleStatus'],
												'Secondary Allele reference', self.genotype_flags['SecondaryAlleleReference'],
												'Secondary Allele original', self.genotype_flags['SecondaryAlleleOriginal'],
												'\nCCG Flags', '',
												'CCG Zygosity Disconnect', self.genotype_flags['CCGZygDisconnect'],
												'CCG Peak Ambiguity', self.genotype_flags['CCGPeakAmbiguous'],
												'CCG Density Ambiguity', self.genotype_flags['CCGDensityAmbiguous'],
												'CCG Recall Warning', self.genotype_flags['CCGRecallWarning'],
												'CCG Peak OOB', self.genotype_flags['CCGPeakOOB'],
												'\nCAG Flags', '',
												'CAG Peak Ambiguity', self.genotype_flags['CAGPeakAmbiguous'],
												'CAG Density Ambiguity', self.genotype_flags['CAGDensityAmbiguous'],
												'CAG Recall Warning', self.genotype_flags['CAGRecallWarning'],
												'CAG Peak OOB', self.genotype_flags['CAGPeakOOB'],
												'CAG Backwards Slippage', self.genotype_flags['CAGBackwardsSlippage'],
												'CAG Forwards Slippage', self.genotype_flags['CAGForwardSlippage'],
												'\nOther Flags', '',
												'DSP Correction', self.genotype_flags['DSPCorrection'],
												'FPSP Disconnect', self.genotype_flags['FPSPDisconnect'],
												'LowRead Distributions', self.genotype_flags['LowReadDistributions'],
												'Potential SVM Failure', self.genotype_flags['SVMPossibleFailure'],
												'Homozygous Haplotype', self.genotype_flags['PotentialHomozygousHaplotype'],
												'Haplotype Interp Distance', self.genotype_flags['PHHInterpDistance'],
												'Peak Expansion Skew', self.genotype_flags['PeakExpansionSkew'],
												'Neighbouring Peaks', self.genotype_flags['NeighbouringPeaks'],
												'Diminished Peak', self.genotype_flags['DiminishedPeak'],
												'Diminished Peak Uncertainty', self.genotype_flags['DiminishedUncertainty'])
		sample_file = open(sample_report_name, 'w')
		sample_file.write(sample_report)
		sample_file.close()

		##
		## Check if we padded our forward before returning into report
		if self.genotype_flags['AlignmentPadding']: fwdist = self.forward_distr_padded
		else: fwdist = self.forward_distribution

		report = {'ForwardDistribution':fwdist,
				  'ReverseDistribution':self.reverse_distribution,
				  'PrimaryAllele':self.genotype_flags['PrimaryAllele'],
				  'SecondaryAllele':self.genotype_flags['SecondaryAllele'],
				  'PredictionConfidence':self.prediction_confidence,
				  'PrimaryAlleleStatus':self.genotype_flags['PrimaryAlleleStatus'],
				  'PrimaryAlleleReference':self.genotype_flags['PrimaryAlleleReference'],
				  'PrimaryAlleleOriginal':self.genotype_flags['PrimaryAlleleOriginal'],
				  'SecondaryAlleleStatus':self.genotype_flags['SecondaryAlleleStatus'],
				  'SecondaryAlleleReference':self.genotype_flags['SecondaryAlleleReference'],
				  'SecondaryAlleleOriginal':self.genotype_flags['SecondaryAlleleOriginal'],
				  'PrimaryMosaicism':self.genotype_flags['PrimaryMosaicism'],
				  'SecondaryMosaicism':self.genotype_flags['SecondaryMosaicism'],
				  'ThresholdUsed':self.genotype_flags['ThresholdUsed'],
				  'RecallCount':self.genotype_flags['RecallCount'],
				  'AlignmentPadding':self.genotype_flags['AlignmentPadding'],
				  'SVMPossibleFailure':self.genotype_flags['SVMPossibleFailure'],
				  'PotentialHomozygousHaplotype':self.genotype_flags['PotentialHomozygousHaplotype'],
				  'PHHIntepDistance':self.genotype_flags['PHHInterpDistance'],
				  'NeighbouringPeaks':self.genotype_flags['NeighbouringPeaks'],
				  'DiminishedPeak':self.genotype_flags['DiminishedPeak'],
				  'DiminishedUncertainty':self.genotype_flags['DiminishedUncertainty'],
				  'PeakExpansionSkew': self.genotype_flags['PeakExpansionSkew'],
				  'CCGZygDisconnect':self.genotype_flags['CCGZygDisconnect'],
				  'CCGPeakAmbiguous':self.genotype_flags['CCGPeakAmbiguous'],
				  'CCGDensityAmbiguous':self.genotype_flags['CCGDensityAmbiguous'],
				  'CCGRecallWarning':self.genotype_flags['CCGRecallWarning'],
				  'CCGPeakOOB':self.genotype_flags['CCGPeakOOB'],
				  'CAGPeakAmbiguous':self.genotype_flags['CAGPeakAmbiguous'],
				  'CAGDensityAmbiguous':self.genotype_flags['CAGDensityAmbiguous'],
				  'CAGRecallWArning':self.genotype_flags['CAGRecallWarning'],
				  'CAGPeakOOB':self.genotype_flags['CAGPeakOOB'],
				  'CAGBackwardsSlippage':self.genotype_flags['CAGBackwardsSlippage'],
				  'CAGForwardSlippage':self.genotype_flags['CAGForwardSlippage'],
				  'FPSPDisconnect':self.genotype_flags['FPSPDisconnect'],
				  'DSPCorrection':self.genotype_flags['DSPCorrection'],
				  'LowReadDistributions':self.genotype_flags['LowReadDistributions']}

		return report

	def get_report(self):
		"""
		Function to just return the report for this class object from the point of calling
		:return: a report. wow
		"""
		return self.gtype_report

class SequenceTwoPass:
	def __init__(self, prediction_path, input_distribution, peak_target, graph_parameters, zygosity_state, contig_stage):
		"""
		Class that will be used as an object for each genotyping stage of the GenotypePrediction pipe
		Each function within this class has it's own doctstring for further explanation
		This class is called into an object for each of CCG/CAG deterministic stages

		:param prediction_path: Output path to save all resultant files from this process
		:param input_distribution: Distribution to put through the two-pass (CAG or CCG..)
		:param peak_target: Number of peaks we expect to see in this current distribution
		:param graph_parameters: Parameters (names of axes etc..) for saving results to graph
		:param zygosity_state: hetero/homozygous (labelling indexing issues require this)
		"""

		##
		## Variables for this instance of this object
		self.prediction_path = prediction_path
		self.input_distribution = input_distribution
		self.peak_target = peak_target
		self.bin_count = graph_parameters[0]
		self.filename = graph_parameters[1]
		self.graph_title = graph_parameters[2]
		self.axes = graph_parameters[3]
		self.zygosity_state = zygosity_state
		self.contig_stage = contig_stage
		self.instance_parameters = {}

		##
		## Potential warnings raised in this instance/useful variables
		self.CCGDensityAmbiguous = False
		self.CCGExpansionSkew = False
		self.CCGPeakAmbiguous = False
		self.CCGPeakOOB = False
		self.PotentialHomozygousHaplotype = False
		self.PHHInterpDistance = 0.0
		self.NeighbouringPeaks = False
		self.DiminishedPeak = False
		self.DiminishedUncertainty = False
		self.PeakExpansionSkew = False
		self.CAGDensityAmbiguous= False
		self.CAGPeakAmbiguous = False
		self.CAGPeakOOB = False
		self.CAGBackwardsSlippage = False
		self.CAGForwardSlippage = False
		self.ThresholdUsed = 0
		self.RecallCount = 0

	def histogram_generator(self, filename, graph_title, axes, plot_flag):
		"""
		Generate histogrm of kernel density estimation for this instance of 2PA
		:param filename: Filename for graph to be saved as..
		:param graph_title: self explanatory
		:param axes: self explanatory
		:param plot_flag: True? Do. False? Don't.
		:return: histogram, bins
		"""

		##
		## Generate KDE histogram and plot to graph
		hist, bins = np.histogram(self.input_distribution, bins=self.bin_count, density=True)
		if plot_flag:
			plt.figure(figsize=(10,6))
			bin_width = 0.7 * (bins[1] - bins[0])
			center = (bins[:-1] + bins[1:]) / 2
			plt.title(graph_title)
			plt.xlabel(axes[0])
			plt.ylabel(axes[1])
			##TODO plt.legend([])
			plt.bar(center, hist, width=bin_width)
			plt.savefig(os.path.join(self.prediction_path, filename), format='pdf')
			plt.close()

		##
		## Check the number of densities that exist within our histogram
		## If there are many (>2) values that are very low density (i.e. relevant)
		## then raise the flag for density ambiguity -- there shouldn't be many values so issue with data
		density_frequency = Counter(hist)
		for key, value in density_frequency.iteritems():
			if not key == np.float64(0.0) and value > 2:
				if self.contig_stage == 'CCG': self.CCGDensityAmbiguous = True
				if self.contig_stage == 'CAG': self.CAGDensityAmbiguous = True

		##
		## Return histogram and bins to where this function was called
		return hist, bins

	@staticmethod
	def peak_clarity(peak_target, hist_list, major_bin, major_sparsity, minor_bin=None, minor_sparsity=None):
		"""
		Function to determine how clean a peak is (homo/hetero)
		Look at densities around each supposed peak, and if the value is close then increment a count
		if the count is above a threshold, return False to indicate failure (and raise a flag)
		:param peak_target: hetero/homo
		:param hist_list: list of histogram under investigation
		:param major_bin: bin of hist of major peak
		:param major_sparsity: sparsity value of that
		:param minor_bin: bin of hist of minor peak
		:param minor_sparsity: sparsity value of that
		:return: True/False
		"""
		clarity_count = 0
		if peak_target == 1:
			major_slice = hist_list[int(major_bin) - 2:int(major_bin) + 2]
			for density in major_slice:
				if np.isclose(major_sparsity, density):
					clarity_count += 1
			if clarity_count > 3:
				return False
		if peak_target == 2:
			major_slice = hist_list[int(major_bin) - 2:int(major_bin) + 2]
			minor_slice = hist_list[int(minor_bin) - 2:int(minor_bin) + 2]
			for density in major_slice:
				if np.isclose(major_sparsity, density):
					clarity_count += 1
			for density in minor_slice:
				if np.isclose(minor_sparsity, density):
					clarity_count += 1
			if clarity_count > 5:
				return False
		return True

	def density_estimation(self, plot_flag):
		"""
		Denisity estimate for a given input distribution (self.input_distribution)
		Use KDE to determine roughly where peaks should be located, peak distances, etc
		Plot graphs for visualisation, return information to origin of call
		:param plot_flag: do we plot a graph or not? (CCG:No,CAG:No) -- may change
		:return: {dictionary of estimated attributes for this input}
		"""

		##
		## Set up variables for this instance's run of density estimation
		## and generate a dictionary to be modified/returned
		distro_list = list(self.input_distribution)
		major_estimate = None; minor_estimate = None
		peak_distance = None; peak_threshold = None
		estimated_attributes = {'PrimaryPeak':major_estimate,
								'SecondaryPeak':minor_estimate,
								'PeakDistance':peak_distance,
								'PeakThreshold':peak_threshold}

		##
		## Begin density estimation!
		## By default, runs in heterozygous assumption
		## If instance requires homozygous then tailor output instead of re-running
		major_estimate = max(self.input_distribution); major_index = distro_list.index(major_estimate)
		minor_estimate = max(n for n in distro_list if n!=major_estimate); minor_index = distro_list.index(minor_estimate)

		##
		## Check that N-1 of <MAJOR> is not <MINOR> (i.e. slippage)
		## If so, correct for minor == 3rd highest and raise error flag!
		if minor_index == major_index-1:
			literal_minor_estimate = max(n for n in distro_list if n!=major_estimate and n!=minor_estimate)
			literal_minor_index = distro_list.index(literal_minor_estimate)
			minor_estimate = literal_minor_estimate
			minor_index = literal_minor_index

		##
		## Actual execution of the Kernel Density Estimation histogram
		hist, bins = self.histogram_generator(self.filename, self.graph_title, self.axes, plot_flag)
		hist_list = list(hist)

		##
		## Determine which bin in the density histogram our estimate values reside within
		## -1 because for whatever reason np.digitize adds one to the literal index
		major_estimate_bin = np.digitize([major_estimate], bins)-2
		minor_estimate_bin = np.digitize([minor_estimate], bins)-1

		##
		## Relevant densities depending on zygosity of the current sample
		major_estimate_sparsity = None
		if self.peak_target == 1:
			major_estimate_sparsity = min(n for n in hist if n!=0)
			peak_distance = 0
			if not self.peak_clarity(self.peak_target, hist_list, major_estimate_bin, major_estimate_sparsity):
				if self.contig_stage == 'CCG': self.CCGPeakAmbiguous = True
				if self.contig_stage == 'CAG': self.CAGPeakAmbiguous = True
		if self.peak_target == 2:
			major_estimate_sparsity = min(n for n in hist if n!=0)
			minor_estimate_sparsity = min(n for n in hist if n!=0 and n!=major_estimate_sparsity)
			peak_distance = np.absolute(major_index - minor_index)
			if not self.peak_clarity(self.peak_target, hist_list, major_estimate_bin, major_estimate_sparsity, minor_estimate_bin, minor_estimate_sparsity):
				if self.contig_stage == 'CCG': self.CCGPeakAmbiguous = True
				if self.contig_stage == 'CAG': self.CAGPeakAmbiguous = True

		##
		## Check for multiple low densities in distribution
		fuzzy_count = 0
		for density in hist_list:
			if np.isclose(major_estimate_sparsity, density):
				fuzzy_count+=1
		if fuzzy_count > 3:
			if self.contig_stage == 'CCG': self.CCGDensityAmbiguous = True
			if self.contig_stage == 'CAG': self.CAGDensityAmbiguous = True

		##
		## Determine Thresholds for this instance sample
		peak_threshold = 0.50
		if self.contig_stage == 'CCG':
			if self.CCGExpansionSkew:
				if self.peak_target == 2:
					peak_threshold -= 0.05
			if self.CCGDensityAmbiguous:
				peak_threshold -= 0.075
			if self.CCGPeakAmbiguous:
				peak_threshold -= 0.10

		if self.contig_stage == 'CAG':
			if self.PeakExpansionSkew:
				if self.peak_target == 2:
					peak_threshold -= 0.05
			if self.CAGDensityAmbiguous:
				peak_threshold -= 0.075
			if self.CAGPeakAmbiguous:
				peak_threshold -= 0.10

		##
		## Preparing estimated attributes for return
		if self.peak_target == 1:
			estimated_attributes['PrimaryPeak'] = major_index+1
			estimated_attributes['SecondaryPeak'] = major_index+1
		if self.peak_target == 2:
			estimated_attributes['PrimaryPeak'] = major_index+1
			estimated_attributes['SecondaryPeak'] = minor_index+1
		estimated_attributes['PeakDistance'] = peak_distance
		estimated_attributes['PeakThreshold'] = peak_threshold

		return estimated_attributes

	def differential_peaks(self, first_pass, fod_params, threshold_bias, fail_state=False, fod_recall=False):
		"""
		Function which takes in parameters gathered from density estimation
		and applies them to a First Order Differential peak detection algorithm
		to more precisely determine the peak (and thus, genotype) of a sample
		:param first_pass: Dictionary of results from KDE
		:param fod_params: Parameters for graphs made in this function
		:param threshold_bias: Bool for whether this call is a re-call or not (lower threshold if True)
		:param fail_state: did this FOD fail or not?
		:param fod_recall: do we need to do a local re-call?
		:return: dictionary of results from KDE influenced FOD
		"""

		##
		## Get Peak information from the KDE dictionary
		## If threshold_bias == True, this is a recall, so lower threshold
		## but ensure the threshold stays within the expected ranges
		peak_distance = first_pass['PeakDistance']
		peak_threshold = first_pass['PeakThreshold']
		if threshold_bias or fod_recall:
			self.RecallCount+=1
			if self.RecallCount > 7: raise Exception('7+ recalls. Unable to determine genotype.\n')
			first_pass['PeakThreshold'] -= 0.06
			peak_threshold -= 0.06
			peak_threshold = max(peak_threshold,0.05)
		self.ThresholdUsed = peak_threshold

		##
		## Graph Parameters expansion
		linspace_dimensionality = fod_params[0]; graph_title = fod_params[1]
		axes = fod_params[2]; filename = fod_params[3]

		##
		## Create planar space for plotting
		## Send paramters to FOD
		## Increment results by 1 (to resolve 0 indexing)
		x = np.linspace(linspace_dimensionality[0], linspace_dimensionality[1], linspace_dimensionality[2])
		buffered_y = np.asarray([0] + list(self.input_distribution))
		y = self.input_distribution
		peak_indexes = peakutils.indexes(y, thres=peak_threshold, min_dist=peak_distance-1)
		fixed_indexes = np.array(peak_indexes+1)

		##
		## Check that we didn't get too many peaks..
		if self.contig_stage == 'CCG':
			if len(fixed_indexes) > 2:
				self.CCGPeakOOB = True
		if self.contig_stage == 'CAG':
			if len(fixed_indexes) > 2:
				self.CAGPeakOOB = True

		##
		## Plot Graph!
		## Set up dimensions for plotting
		plt.figure(figsize=(10,6)); plt.title(graph_title)
		plt.xlabel(axes[0]); plt.ylabel(axes[1])

		##
		## Set appropriate range size for CCG/CAG graph dimension
		if self.contig_stage == 'CCG': plt.xticks(np.arange(0,21,1)); plt.xlim(1,20)
		if self.contig_stage == 'CAG': plt.xticks(np.arange(0,201,50)); plt.xlim(1,200)

		##
		## Try to assign peaks to the appropriate indexes
		## If we're expecting one peak (CCG Het) then it's simple to do so..
		## Index Error = too few peaks were called, so we can fail and re-call

		if self.peak_target == 1:
			try:
				first_pass['PrimaryPeak'] = fixed_indexes.item(0)
				first_pass['SecondaryPeak'] = fixed_indexes.item(0)
			except IndexError:
				fail_state = True
		## However, if we're expecting 2 peaks (CCG Hom) then it's more complicated
		## If there are not enough peaks called (1 instead of 2) then the current sample may fall into:
		## -- Homozygous Haplotype.. a true homozygote; CAGxCCGyCAGxCCGy
		## -- Diminished Peak.. there are two peaks but one is significantly smaller than the main, and
		##    lowering threshold to detect it would just introduce noise / worsen results
		## -- Neighbouring Peak.. there are two peaks within this sample, they are just right next to each other
		## And thus the following deterministic functions figure out which rare-case our sample fits into
		if self.peak_target == 2 and self.contig_stage == 'CAG':
			try:
				first_pass['PrimaryPeak'] = fixed_indexes.item(0)
				first_pass['SecondaryPeak'] = fixed_indexes.item(1)
			except IndexError:
				grep_list = [x,y,buffered_y,peak_indexes]
				if self.RecallCount < 6:
					fail_state = True
				else:
					homozygous_fail, interp_distance = self.homozygous_deterministic(grep_list)
					if homozygous_fail:
						neighbour_fail, neighbour_peaks = self.neighbour_deterministic(grep_list)
						if neighbour_fail:
							diminished_fail, diminished_peaks = self.diminished_deterministic(grep_list)
							if diminished_fail:
								fail_state = True
							else:
								self.DiminishedPeak = True
								first_pass['PrimaryPeak'] = diminished_peaks.item(0)
								first_pass['SecondaryPeak'] = diminished_peaks.item(1)
						else:
							self.NeighbouringPeaks = True
							first_pass['PrimaryPeak'] = neighbour_peaks.item(0)
							first_pass['SecondaryPeak'] = neighbour_peaks.item(1)
					else:
						self.PotentialHomozygousHaplotype = True
						self.PHHInterpDistance = interp_distance
						first_pass['PrimaryPeak'] = fixed_indexes.item(0)
						first_pass['SecondaryPeak'] = fixed_indexes.item(0)

		##
		## CCG search dimensions are so small that the only issue ever will be neighbouring peaks
		## So if we expect 2 peaks, and don't have 2, pass to neighbouring_deterministic()
		## If that fails.. CCG unsalvagable and thus CAG can't be acquired -- sample failure
		if self.peak_target == 2 and self.contig_stage == 'CCG':
			try:
				first_pass['PrimaryPeak'] = fixed_indexes.item(0)
				first_pass['SecondaryPeak'] = fixed_indexes.item(1)
			except IndexError:
				maxccg = max(list(self.input_distribution))
				maxmoccg = max(n for n in list(self.input_distribution) if n!= maxccg)
				first_pass['PrimaryPeak'] = list(self.input_distribution).index(maxccg)+1
				first_pass['SecondaryPeak'] = list(self.input_distribution).index(maxmoccg)+1

		##
		## Double check number of returned peaks
		if self.contig_stage == 'CAG' and self.peak_target == 1 and len(peak_indexes) == 2:
			self.CAGPeakOOB = True

		##
		## Re-create indexes incase that we had a haplotype/neighbouring flag issue
		fixed_indexes = np.array([first_pass['PrimaryPeak'], first_pass['SecondaryPeak']])

		##
		## In the case of heterozygous distributions, check that the expanded peak
		## is not > in value than the normal peak; this is worth informing the user about
		if self.zygosity_state == 'HOMO':
			majr = list(self.input_distribution)[(fixed_indexes-1).item(0)]
			minr = list(self.input_distribution)[(fixed_indexes-1).item(1)]
			if minr > majr and peak_distance > 1: self.PeakExpansionSkew = True

		##
		## Execute actual plotting last, incase of homozyg haplotype/neighbouring peaks
		## Plot graph and identified peaks; label appropriately based on size of fixed_indexes
		pplot(x,buffered_y,fixed_indexes)
		if fixed_indexes.item(0) == fixed_indexes.item(1): plt.legend(['Genotype: {}'.format(fixed_indexes.item(0))])
		else: plt.legend(['Genotype: {},{}'.format(fixed_indexes.item(0),fixed_indexes.item(1))])
		plt.savefig(os.path.join(self.prediction_path,filename), format='pdf')
		plt.close()

		return fail_state, first_pass

	def diminished_deterministic(self, peak_info, fail_state=False):
		"""
		Function to do a low-pass inspection along the entire distribution, in chunks
		Allows us to gauge whether this input distribution has a secondary peak which is considerably much lower
		than the current main peak prediction in terms of literal read count value, but is still definitely a peak
		within it's own right. (e.g. main peak = 20k reads, sub peak = 500). We do this as continually lowering
		the threshold of the main peak calling algorithm will just introduce noise beyond a certain point; this
		function allows us to comb over the details of the entire distribution and ensure that we get the correct
		second peak...
		:param peak_info: list of peak information to be utilised within this investigation
		:param fail_state: whether or not this function hit the fail conditions
		:return: fail_state, new_peaks [x, y]
		"""

		##
		## Get the relevant information for this investigation
		n = self.input_distribution[peak_info[3]]
		peak_resolutions = [[25,8,6],[40,5,3]]
		resolution_peaks = []

		##
		## Loop over two different slicing contexts; to ensure we don't get too many peaks in one slice
		for resolution in peak_resolutions:
			##
			## Slice the distribution we're working with so we can check lower threshold areas specifically
			sliced_distribution = np.split(self.input_distribution, resolution[0])
			slice_index_dict = {}
			for i in range(0,len(sliced_distribution)):
				slice_indexes = peakutils.indexes(sliced_distribution[i], thres=0.025, min_dist=resolution[2])
				slice_index_dict[i+1] = {'SlicePeakIndex':slice_indexes,
										 'SlicePeakValue':sliced_distribution[i][slice_indexes],
										 'SliceDistro':sliced_distribution[i]}

			##
			## Loop over every low-pass distribution slice to determine the 'candidate' for the diminished peak
			## if the current Slice Peak Value is > the previously seen max candidate, and not = n (real peak)
			## then current maximum candidate for diminished peak = current Slice Peak Value
			## Set objects accordingly..
			current_candidate = 0
			current_candidate_slice = 0
			current_candidate_index = 0
			for dkey, ddata in sorted(slice_index_dict.iteritems()):
				if ddata['SlicePeakValue'] > current_candidate and ddata['SlicePeakValue'] != n:
					current_candidate = ddata['SlicePeakValue']
					current_candidate_slice = int(dkey)
					current_candidate_index = ddata['SlicePeakIndex']

			##
			## Calculate the literal (self.input_distribution based) index of this supposed candidate diminished peak
			## Then return an array of new peaks, after checking the index int value is in the right order (low, high)..
			subpeak_literal = np.array(((current_candidate_slice-1) * resolution[1]) + current_candidate_index)
			if int(subpeak_literal) < int(peak_info[3]):
				new_peaks = np.array([subpeak_literal.item(0), peak_info[3].item(0)])
			else:
				new_peaks = np.array([peak_info[3].item(0), subpeak_literal.item(0)])

			##
			## If the two resolutions produced a differing prediction.. check that the values make sense
			## I.E. even if a resolution detected a peak, ensure that the literal read count value is likely (T1/2/3/4)
			topone = max(self.input_distribution)
			toptwo = max(n for n in self.input_distribution if n!=topone)
			topthree = max(n for n in self.input_distribution if n!=topone and n!=toptwo)
			topfour = max(n for n in self.input_distribution if n!=topone and n!=toptwo and n!=topthree)

			##
			## Once the top4 have been discerned; loop over the current resolution's predicitons
			## If both peaks in this allele are determined to confine within the desired logic, score 2
			## If one, score 1; if none, score 0 (fail)
			peak_register_score = 0
			for value in new_peaks:
				if self.input_distribution[value] not in [topone, toptwo, topthree, topfour]:
					list(new_peaks).remove(value); continue
				else: peak_register_score += 1
			if peak_register_score == 0: fail_state = True
			else: resolution_peaks.append([new_peaks, peak_register_score])

		##
		## Now that we have the two slice resolution peak predictions; check and take the best scoring one
		## If the scores are both 1... hmm.. raise flag for inspection
		current_resolution_candidate = None
		for i in range(0,1):
			try:
				firstreso_peak = resolution_peaks[i][0]; firstreso_score = resolution_peaks[i][1]
				secndreso_peak = resolution_peaks[i+1][0]; secndreso_score = resolution_peaks[i+1][1]
				if firstreso_score > secndreso_score: current_resolution_candidate = firstreso_peak
				if secndreso_score > firstreso_score: current_resolution_candidate = secndreso_peak
				if firstreso_score == secndreso_score:
					current_resolution_candidate = firstreso_peak
					self.DiminishedUncertainty = True
			except IndexError:
				pass

		##
		## Rudimentary fail state catcher so that we don't force a neighbouring peak
		## into a diminished peak determination..
		## If the literal read count value is so small that it couldn't possibly be a diminished peak
		## Then we fail.. pass onto neighbouring deterministic
		for peak in current_resolution_candidate:
			if np.isclose([list(self.input_distribution)[peak]], [0], atol=25):
				fail_state = True

		##
		## Return our fail_state and new peaks array
		## Adding one to the peaks to resolve inner (0-index) and literal(1-index) issue
		new_peaks = np.array(current_resolution_candidate + 1)
		return fail_state, new_peaks

	def homozygous_deterministic(self, peak_info, fail_state=False):
		"""
		Function to determine whether a peak is a potetnail homozygous haplotype or a neighbouring peak
		Fill out this docstring later
		:param peak_info: list of data about our suspected peaks
		:param fail_state: whether this function passes or not
		:return: fail_state, interp_distance
		"""

		##
		## Subroutine to do testing on a given list of data
		def resolution_tester(dset):
			pass_total = 0
			for test in dset:
				if np.isclose(np.around(test[0], decimals=3),test[1],atol=test[2]):
					pass_total += 1
			return pass_total

		##
		## Calculate the percentage drop-off for our suspected peak
		## If the thresholds are met, do interp on the peak
		nmt = self.input_distribution[peak_info[3]-2]; nmo = self.input_distribution[peak_info[3]-1]
		n = self.input_distribution[peak_info[3]]; npo = self.input_distribution[peak_info[3]+1]
		npt = self.input_distribution[peak_info[3]+2]; nmt_n = nmt / n; nmo_n = nmo / n
		npo_n = npo / n; npt_n = npt / n

		##
		## Different categories of peak clarity require different dropoff thresholds
		## A clean peak (i.e. pass for homozygous haplotype) == Ultra, VHigh, High
		## A 'spread' peak (i.e. neighbouring peak.. not homozygous) == Medium, Low, VLow
		differential_qualities = {'Ultra':[[[nmt_n],[0.015],[0.005]], [[nmo_n],[0.15],[0.05]], [[npo_n],[0.005],[0.005]], [[npt_n],[0.00050],[0.0005]]],
								  'VHigh':[[[nmt_n],[0.025],[0.005]], [[nmo_n],[0.20],[0.05]], [[npo_n],[0.010],[0.005]], [[npt_n],[0.00075],[0.0005]]],
								  'High':[[[nmt_n],[0.050],[0.025]], [[nmo_n],[0.30],[0.05]], [[npo_n],[0.015],[0.005]], [[npt_n],[0.00100],[0.0010]]],
								  'Medium':[[[nmt_n],[0.125],[0.025]], [[nmo_n],[0.375],[0.05]], [[npo_n],[0.02],[0.075]], [[npt_n],[0.002],[0.001]]],
								  'Low':[[[nmt_n],[0.275],[0.050]], [[nmo_n],[0.550],[0.10]], [[npo_n],[0.03],[0.075]], [[npt_n],[0.003],[0.001]]],
								  'VLow':[[[nmt_n],[0.450],[0.075]], [[nmo_n],[0.700],[0.15]], [[npo_n],[0.05],[0.010]], [[npt_n],[0.005],[0.002]]]}

		##
		## Determine which quality of peak has the highest passrate for the four data points
		highest_qual = None
		highest_rate = 0
		for quality, dropoff_values in differential_qualities.iteritems():
			passrate = resolution_tester(dropoff_values)
			if passrate > highest_rate:
				highest_rate = passrate
				highest_qual = quality

		##
		## If the sample was a homozygous shape, fit gaussian to data
		## If gaussian within 0.3 of suspected homozygous peak, it's real
		## otherwise, probably neighbouring peaks, so send to that function
		interp_distance = 0.0
		if highest_qual in ['Ultra','VHigh','High']:
			peaks_interp = peakutils.interpolate(peak_info[0], peak_info[1], ind=peak_info[3])
			if np.isclose([peaks_interp],[float(peak_info[3])], atol=0.30):
				interp_distance = abs(peaks_interp - float(peak_info[3]))
			else:
				fail_state = True

		return fail_state, interp_distance

	def neighbour_deterministic(self, peak_info, fail_state=False):
		"""
		Function to determine whether a sample which was not a homozygous haplotype is infact
		a heterozygous normal, with target peaks being neighbours to N; either N-1 or N+1
		However, before assuming we are in a neighbouring situation, we do a low-read count pass
		of the distribution incase there are any legitimate discrete peaks which are very small
		compared to the major peak; this is the real 'secondary' peak and will be used if found.
		Otherwise, we follow the neighbouring peak deterministic...
		:param peak_info: [x, y, buffered_y, genotype]
		:param fail_state: whether we pass or fail..
		:return: fail_state (boolean for success), new_peaks (determined neighbour or mini-peak)
		"""

		##
		## Get the relevant information for this investigation
		nmo = self.input_distribution[peak_info[3]-1]
		n = self.input_distribution[peak_info[3]]
		npo = self.input_distribution[peak_info[3]+1]
		new_peaks = np.array([0,0])

		##
		## Discrete check on raw read value of bins
		## Return arrays (indexes corrected for 0-indexing of np, but 1-indexing of real)
		if nmo > npo:
			new_peaks = np.array([peak_info[3],peak_info[3]+1])
		elif npo > nmo:
			new_peaks = np.array([peak_info[3]+1,peak_info[3]+2])
			if n > npo:
				self.CAGBackwardsSlippage = True
		else:
			fail_state = True ## if here.. sample uncallable

		##
		## Return our new genotypes and failstate
		return fail_state, new_peaks

	def get_warnings(self):
		"""
		Function which generates a dictionary of warnings encountered in this instance of SequenceTwoPass
		Dictionary is later sorted into the GenotypePrediction equivalency for returning into a report file
		:return: {warnings}
		"""

		return {'CCGDensityAmbiguous':self.CCGDensityAmbiguous,
				'CCGPeakAmbiguous':self.CCGPeakAmbiguous,
				'CCGPeakOOB':self.CCGPeakOOB,
				'PotentialHomozygousHaplotype':self.PotentialHomozygousHaplotype,
				'PHHInterpDistance':self.PHHInterpDistance,
				'NeighbouringPeaks':self.NeighbouringPeaks,
				'DiminishedPeak':self.DiminishedPeak,
				'DiminishedUncertainty':self.DiminishedUncertainty,
				'PeakExpansionSkew': self.PeakExpansionSkew,
				'CAGDensityAmbiguous':self.CAGDensityAmbiguous,
				'CAGPeakAmbiguous':self.CAGPeakAmbiguous,
				'CAGPeakOOB':self.CAGPeakOOB,
				'CAGBackwardsSlippage':self.CAGBackwardsSlippage,
				'CAGForwardSlippage':self.CAGForwardSlippage,
				'ThresholdUsed':self.ThresholdUsed,
				'RecallCount':self.RecallCount}

class MosaicismInvestigator:
	def __init__(self, genotype, distribution):
		"""
		A class which is called when the functions within are required for somatic mosaicism calculations
		As of now there is only a basic implementation of somatic mosaicism studies but it's WIP
		"""

		self.genotype = genotype
		self.distribution = distribution

	def chunks(self, n):
		"""
		Function which takes an entire sample's distribution (200x20) and split into respective 'chunks'
		I.E. slice one distribution into contigs for each CCG (200x1 x 20)
		:param n: number to slice the "parent" distribution into
		:return: CHUNKZ
		"""

		for i in xrange(0, len(self.distribution), n):
			yield self.distribution[i:i + n]

	@staticmethod
	def arrange_chunks(ccg_slices):
		"""
		Function which takes the sliced contig chunks and orders them into a dataframe for ease of
		interpretation later on in the application. Utilises pandas for the dataframe class since
		it's the easiest to use.
		:param ccg_slices: The sliced CCG contigs
		:return: df: a dataframe which is ordered with appropriate CCG labels.
		"""

		arranged_rows = []
		for ccg_value in ccg_slices:
			column = []
			for i in range(0, len(ccg_value)):
				column.append(ccg_value[i])
			arranged_rows.append(column)

		df = pd.DataFrame({'CCG1': arranged_rows[0], 'CCG2': arranged_rows[1], 'CCG3': arranged_rows[2],
						   'CCG4': arranged_rows[3], 'CCG5': arranged_rows[4], 'CCG6': arranged_rows[5],
						   'CCG7': arranged_rows[6], 'CCG8': arranged_rows[7], 'CCG9': arranged_rows[8],
						   'CCG10': arranged_rows[9], 'CCG11': arranged_rows[10], 'CCG12': arranged_rows[11],
						   'CCG13': arranged_rows[12], 'CCG14': arranged_rows[13], 'CCG15': arranged_rows[14],
						   'CCG16': arranged_rows[15], 'CCG17': arranged_rows[16], 'CCG18': arranged_rows[17],
						   'CCG19': arranged_rows[18], 'CCG20': arranged_rows[19]})

		return df

	@staticmethod
	def get_nvals(df, input_allele):
		"""
		Function to take specific CCG contig sub-distribution from dataframe
		Extract appropriate N-anchored values for use in sommos calculations
		:param df: input dataframe consisting of all CCG contig distributions
		:param input_allele: genotype derived from GenotypePrediction (i.e. scrape target)
		:return: allele_nvals: dictionary of n-1/n/n+1
		"""
		allele_nvals = {}
		cag_value = input_allele[0]
		ccgframe = df['CCG'+str(input_allele[1])]

		try:
			nminus = str(ccgframe[int(cag_value)-2])
			nvalue = str(ccgframe[int(cag_value)-1])
			nplus = str(ccgframe[int(cag_value)])
		except KeyError:
			log.info('{}{}{}{}'.format(clr.red,'shd__ ',clr.end,'N-Value scraping Out of Bounds.'))

		allele_nvals['NMinusOne'] = nminus
		allele_nvals['NValue'] = nvalue
		allele_nvals['NPlusOne'] = nplus

		return allele_nvals

	@staticmethod
	def calculate_mosaicism(allele_values):
		"""
		Function to execute the actual calculations
		Perhaps float64 precision is better? Might not matter for us
		Also required to add additional calculations here to make the 'suite' more robust
		:param allele_values: dictionary of this sample's n-1/n/n+1
		:return: dictionary of calculated values
		"""

		nmo = allele_values['NMinusOne']
		n = allele_values['NValue']
		npo = allele_values['NPlusOne']
		nmo_over_n = 0
		npo_over_n = 0

		try:
			nmo_over_n = int(nmo) / int(n)
			npo_over_n = int(npo) / int(n)
		except ValueError:
			nmo_over_n = float(nmo) / float(n)
			npo_over_n = float(npo) / float(n)
		except ZeroDivisionError:
			log.info('{}{}{}{}'.format(clr.red,'shd__ ',clr.end,' Divide by 0 attempted in Mosaicism Calculation.'))

		calculations = {'NMinusOne':nmo,'NValue':n,'NPlusOne':npo,'NMinusOne-Over-N': nmo_over_n, 'NPlusOne-Over-N': npo_over_n}
		return calculations

	@staticmethod
	def distribution_padder(ccg_dataframe, genotype):
		"""
		Function to ensure all distribution's N will be anchored to the same position in a file
		This is to allow the end user manual insight into the nature of the data (requested for now)
		E.G. larger somatic mosaicism spreads/trends in a distribution + quick sample-wide comparison
		:param ccg_dataframe: dataframe with all CCG contigs
		:param genotype: genotype derived from GenotypePrediction i.e. scrape target
		:return: distribution with appropriate buffers on either side so that N is aligned to same position as all others
		"""
		unpadded_distribution = list(ccg_dataframe['CCG'+str(genotype[1])])
		n_value = genotype[0]

		anchor = 203
		anchor_to_left = anchor - n_value
		anchor_to_right	= anchor_to_left + 200
		left_buffer = ['-'] * anchor_to_left
		right_buffer = ['-'] * (403-anchor_to_right)
		padded_distribution = left_buffer + unpadded_distribution + right_buffer

		return padded_distribution

class DSPResultsGenerator:
	def __init__(self, sequencepair_data, predict_path, processed_atypical):
		"""
		Temporary workaround class for producing distribution graphs when the user wants to trust DSP genotyping
		instead of re-aligning to a custom reference. This will be removed when GenotypePrediction is re-written
		to account for allele-based data rather than distribution-based. Hence this is a messy repetetive piece of shit.
		:param sequencepair_data: current sample pair (fw/rv) data
		:param predict_path: prediction path for the current instance of SHD
		:param processed_atypical: results from DSP atypical allele detection
		"""

		##
		## Class objects of input
		self.data_pair = sequencepair_data
		self.prediction_path = predict_path
		self.processed_atypical = processed_atypical

		##
		## Flags
		self.genotype_flags = {'AlignmentPadding':False, 'PrimaryAllele':(0,0), 'SecondaryAllele':(0,0)}

		##
		## Distributions
		## Unlabelled distributions to utilise for SVM prediction
		## Padded distro = None, in case where SAM aligned to (0-100,0-20 NOT 1-200,1-20), use this
		self.forward_distr_padded = None
		self.forward_distribution = np.empty(shape=(1,1)); self.reverse_distribution = np.empty(shape=(1,1))
		if type(self.data_pair[0]) == str:
			self.forward_distribution = self.scrape_distro(self.data_pair[0])
			self.reverse_distribution = self.scrape_distro(self.data_pair[1])
		if type(self.data_pair[1]) == tuple:
			self.forward_distribution = self.scrape_distro(self.data_pair[0][0])
			self.reverse_distribution = self.scrape_distro(self.data_pair[1][0])
		self.forwardccg_aggregate = self.distribution_collapse(self.forward_distribution, st=True)
		self.reverseccg_aggregate = self.distribution_collapse(self.reverse_distribution)
		self.target_distribution = {}

		##
		## CAG Targets
		if not self.genotype_flags['AlignmentPadding']: forward_utilisation = self.forward_distribution
		else: forward_utilisation = self.forward_distr_padded

		##
		## :: Workflow ::
		## Get alleles in (CAG,CCG) format from input
		## Determine which is normal/expanded (size based)
		## Split CAG target CCG distribution from master distribution
		## Render graphs, save graphs
		## Return dictionary of sample name/path of graphs (for master PDF output)
		self.alleles = self.get_alleles()
		if self.alleles[0][1] > self.alleles[1][1]:
			self.genotype_flags['PrimaryAllele'] = self.alleles[1]
			self.genotype_flags['SecondaryAllele'] = self.alleles[0]
		else:
			self.genotype_flags['PrimaryAllele'] = self.alleles[0]
			self.genotype_flags['SecondaryAllele'] = self.alleles[1]

		for atypical in self.processed_atypical:
			if atypical['EstimatedCAG'] == self.alleles[0][0] and atypical['EstimatedCCG'] == self.alleles[0][1]:
				self.genotype_flags['PrimaryAlleleDict'] = atypical
			if atypical['EstimatedCAG'] == self.alleles[1][0] and atypical['EstimatedCCG'] == self.alleles[1][1]:
				self.genotype_flags['SecondaryAlleleDict'] = atypical

		cag_target_major = self.split_cag_target(forward_utilisation, self.genotype_flags['PrimaryAllele'][1])
		cag_target_minor = self.split_cag_target(forward_utilisation, self.genotype_flags['SecondaryAllele'][1])
		self.target_distribution[self.genotype_flags['PrimaryAllele'][1]] = cag_target_major
		self.target_distribution[self.genotype_flags['SecondaryAllele'][1]] = cag_target_minor
		self.process_alleles()
		self.genotype_report = self.process_report()

	@staticmethod
	def scrape_distro(distributionfi):
		"""
		Function to take the aligned read-count distribution from CSV into a numpy array
		:param distributionfi:
		:return: np.array(data_from_csv_file)
		"""

		##
		## Open CSV file with information within; append to temp list
		## Scrape information, cast to np.array(), return
		placeholder_array = []
		with open(distributionfi) as dfi:
			source = csv.reader(dfi, delimiter=',')
			next(source) #skip header
			for row in source:
				placeholder_array.append(int(row[2]))
			dfi.close()
		unlabelled_distro = np.array(placeholder_array)
		return unlabelled_distro

	@staticmethod
	def split_cag_target(input_distribution, ccg_target):
		"""
		Function to gather the relevant CAG distribution for the specified CCG value
		We gather this information from the forward distribution of this sample pair as CCG reads are
		of higher quality in the forward sequencing direction.
		We split the entire fw_dist into contigs/bins for each CCG (4000 -> 200*20)
		:param input_distribution: input forward distribution (4000d)
		:param ccg_target: target value we want to select the 200 values for
		:return: the sliced CAG distribution for our specified CCG value
		"""

		cag_split = [input_distribution[i:i+200] for i in xrange(0, len(input_distribution), 200)]
		distribution_dict = {}
		for i in range(0, len(cag_split)):
			distribution_dict['CCG'+str(i+1)] = cag_split[i]

		current_target_distribution = distribution_dict['CCG' + str(ccg_target)]
		return current_target_distribution

	def distribution_collapse(self, distribution_array, st=False):
		"""
		Function to take a full 200x20 array (struc: CAG1-200,CCG1 -- CAG1-200CCG2 -- etc CCG20)
		and aggregate all CAG values for each CCG
		:param distribution_array: input dist (should be (1-200,1-20))
		:param st: flag for if we're in forward stage; i.e. input aligned to wrong ref -> assign padded to fwrd
		:return: 1x20D np(array)
		"""

		##
		## Object for CCG split
		ccg_arrays = None

		##
		## Hopefully the user has aligned to the right reference dimensions
		## Check.. if not, hopefully we can pad (and raise flag.. since it is not ideal)
		try:
			ccg_arrays = np.split(distribution_array, 20)
		##
		## User aligned to the wrong reference..
		except ValueError:
			self.genotype_flags['AlignmentPadding'] = True

			##
			## If the distro is this size, they aligned to (0-100,0-20)...
			## Split by 21, append with 99x1's to end of each CCG
			## Trim first entry in new list (CCG0.. lol who even studies that)
			## If we're on a forward distro collapse, assign padded distro (for mosaicism later)
			if len(distribution_array) == 2121:
				altref_split = np.split(distribution_array, 21)
				padded_split = []
				for ccg in altref_split:
					current_pad = np.append(ccg[1:], np.ones(100))
					padded_split.append(current_pad)
				ccg_arrays = padded_split[1:]

				if st:
					self.forward_distr_padded = np.asarray([item for sublist in ccg_arrays for item in sublist])

		##
		## Aggregate each CCG
		ccg_counter = 1
		collapsed_array = []
		for ccg_array in ccg_arrays:
			collapsed_array.append(np.sum(ccg_array))
			ccg_counter+=1
		return np.asarray(collapsed_array)

	def get_alleles(self):

		sample_alleles = []
		for allele in self.processed_atypical:
			singular_allele = (allele['EstimatedCAG'], allele['EstimatedCCG'])
			sample_alleles.append(singular_allele)

		if sample_alleles[0][1] == sample_alleles[1][1]: sample_alleles.sort(key=lambda x: x[0])
		else: sample_alleles.sort(key=lambda x: x[1])

		return sample_alleles

	def process_alleles(self):

		##
		## Generate atypical labels
		allele_labels = []
		for target_allele in self.alleles:
			for atypical_dict in self.processed_atypical:
				if atypical_dict['EstimatedCAG'] == target_allele[0] and atypical_dict['EstimatedCCG'] == target_allele[1]:
					allele_label = 'Allele status: {}\nOriginal Genotype: {}\nLiteral genotype: {}'.format(
						atypical_dict['Status'],atypical_dict['OriginalReference'],atypical_dict['Reference']
					)
					allele_labels.append(allele_label)

		##
		## Render CCG peak detection graph (one graph regardless)
		ccg_idx = [x[1] for x in self.alleles]
		ccg_parameters = [[0,19,20], 'CCG Peaks', ['CCG Value', 'Read Count'], 'CCGPeakDetection.pdf', allele_labels, ccg_idx]
		self.graph_render(ccg_parameters, self.reverseccg_aggregate)

		##
		## Determine CCG zygosity, thus determining CAG graph requirements
		if self.alleles[0][1] == self.alleles[1][1]:
			cag_idx = [x[0] for x in self.alleles]
			cag_parameters = [[0,199,200],'{}{})'.format('CAG Peaks (CCG',str(self.alleles[0][1])),['CAG Value', 'Read Count'], '{}{}{}'.format('CCG',str(self.alleles[0][1]),'-CAGPeakDetection.pdf'), allele_labels, cag_idx]
			self.graph_render(cag_parameters, self.target_distribution[self.genotype_flags['PrimaryAllele'][1]])
		else:
			for ccg_value, cag_distro in self.target_distribution.iteritems():
				cag_idx = []
				if ccg_value == self.alleles[0][1]: cag_idx = []
				if ccg_value == self.alleles[1][1]: cag_idx = [self.alleles[1][0]-1]
				cag_parameters = [[0,199,200],'{}{})'.format('CAG Peaks (CCG',str(ccg_value)),['CAG Value', 'Read Count'], '{}{}{}'.format('CCG',str(ccg_value),'-CAGPeakDetection.pdf'), allele_labels, cag_idx]
				self.graph_render(cag_parameters, cag_distro)

	def graph_render(self, dimension_params, input_distribution):

		##
		## Graph argument expansion
		linspace_dim = dimension_params[0]
		graph_title = dimension_params[1]
		axes_labels = dimension_params[2]
		filename = dimension_params[3]
		allele_labels = dimension_params[4]
		curr_idx = dimension_params[5]

		##
		## Create planar space for plotting
		## Increment results by 1 (to resolve 0 indexing)
		x = np.linspace(linspace_dim[0], linspace_dim[1], linspace_dim[2])
		#buffered_y = np.asarray([0] + list(input_distribution))
		y = input_distribution

		##
		## Plot Graph!
		## Set up dimensions for plotting
		plt.figure(figsize=(13,8)); plt.title(graph_title)
		plt.xlabel(axes_labels[0]); plt.ylabel(axes_labels[1])

		##
		## Execute actual plotting
		## Generate transparent handles for legend
		## Append atypical legend text.. highlight atypical allele in red
		pplot(x, y, curr_idx)
		handle = Rectangle((0,0), 0, 0, alpha=0.0)
		leg = plt.legend([handle, handle], allele_labels, framealpha=0, loc='best', handlelength=0)
		for text in leg.get_texts():
			if 'Atypical' in text.get_text(): text.set_color("red")

		plt.savefig(os.path.join(self.prediction_path, filename), format='pdf')
		plt.close()

	def process_report(self):

		##
		## Hideous string based report for individual samples
		## Will get changed at a later date
		sample_name = self.prediction_path.split('/')[-2]
		sample_report_name = os.path.join(self.prediction_path, sample_name+'QuickReport.txt')
		sample_report = '{}: {}\n{}: {}\n{}: {}\n{}: {}%\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n' \
						'{}: {}\n{}: {}\n{}: {}\n{}: {}\n{}: {}\n'.format('File Name', sample_name,
												'Primary Allele', self.genotype_flags['PrimaryAllele'],
												'Secondary Allele', self.genotype_flags['SecondaryAllele'],
												'Prediction Confidence', 'Atypical_DSP',
												'Threshold Used', 'N/A',
												'Recall Count', 'N/A',
												'Alignment Padding', 'N/A',
												'\nAtypical Flags', '',
												'Primary Allele status', self.genotype_flags['PrimaryAlleleDict']['Status'],
												'Primary Allele reference', self.genotype_flags['PrimaryAlleleDict']['Reference'],
												'Primary Allele original', self.genotype_flags['PrimaryAlleleDict']['OriginalReference'],
												'Secondary Allele status', self.genotype_flags['SecondaryAlleleDict']['Status'],
												'Secondary Allele reference', self.genotype_flags['SecondaryAlleleDict']['Reference'],
												'Secondary Allele original', self.genotype_flags['SecondaryAlleleDict']['OriginalReference'],
												'\nCCG Flags', '',
												'CCG Zygosity Disconnect', 'N/A',
												'CCG Peak Ambiguity', 'N/A',
												'CCG Density Ambiguity', 'N/A',
												'CCG Recall Warning', 'N/A',
												'CCG Peak OOB', 'N/A',
												'\nCAG Flags', '',
												'CAG Peak Ambiguity', 'N/A',
												'CAG Density Ambiguity', 'N/A',
												'CAG Recall Warning', 'N/A',
												'CAG Peak OOB', 'N/A',
												'CAG Backwards Slippage', 'N/A',
												'CAG Forwards Slippage', 'N/A',
												'\nOther Flags', '',
												'FPSP Disconnect', 'N/A',
												'LowRead Distributions', 'N/A',
												'Potential SVM Failure', 'N/A',
												'Homozygous Haplotype', 'N/A',
												'Haplotype Interp Distance', 'N/A',
												'Peak Expansion Skew', 'N/A',
												'Neighbouring Peaks', 'N/A',
												'Diminished Peak', 'N/A',
												'Diminished Peak Uncertainty', 'N/A')
		sample_file = open(sample_report_name, 'w')
		sample_file.write(sample_report)
		sample_file.close()

		report = {'ForwardDistribution':'N/A',
				  'ReverseDistribution':'N/A',
				  'PrimaryAllele':self.genotype_flags['PrimaryAllele'],
				  'SecondaryAllele':self.genotype_flags['SecondaryAllele'],
				  'PredictionConfidence':'Atypical_DSP',
				  'PrimaryAlleleStatus': self.genotype_flags['PrimaryAlleleDict']['Status'],
				  'PrimaryAlleleReference': self.genotype_flags['PrimaryAlleleDict']['Reference'],
				  'PrimaryAlleleOriginal': self.genotype_flags['PrimaryAlleleDict']['OriginalReference'],
				  'SecondaryAlleleStatus': self.genotype_flags['SecondaryAlleleDict']['Status'],
				  'SecondaryAlleleReference': self.genotype_flags['SecondaryAlleleDict']['Reference'],
				  'SecondaryAlleleOriginal': self.genotype_flags['SecondaryAlleleDict']['OriginalReference'],
				  'PrimaryMosaicism':'N/A',
				  'SecondaryMosaicism':'N/A',
				  'ThresholdUsed':'N/A',
				  'RecallCount':'N/A',
				  'AlignmentPadding':'N/A',
				  'SVMPossibleFailure':'N/A',
				  'PotentialHomozygousHaplotype':'N/A',
				  'PHHIntepDistance':'N/A',
				  'NeighbouringPeaks':'N/A',
				  'DiminishedPeak':'N/A',
				  'DiminishedUncertainty':'N/A',
				  'PeakExpansionSkew':'N/A',
				  'CCGZygDisconnect':'N/A',
				  'CCGPeakAmbiguous':'N/A',
				  'CCGDensityAmbiguous':'N/A',
				  'CCGRecallWarning':'N/A',
				  'CCGPeakOOB':'N/A',
				  'CAGPeakAmbiguous':'N/A',
				  'CAGDensityAmbiguous':'N/A',
				  'CAGRecallWArning':'N/A',
				  'CAGPeakOOB':'N/A',
				  'CAGBackwardsSlippage':'N/A',
				  'CAGForwardSlippage':'N/A',
				  'FPSPDisconnect':'N/A',
				  'LowReadDistributions':'N/A'
		}

		return report

	def get_report(self):

		return self.genotype_report